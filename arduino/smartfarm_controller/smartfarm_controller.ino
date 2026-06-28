#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_SHT31.h>
#include <BH1750.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// Adjust these pins to your wiring.
const uint8_t PIN_SOIL_MOISTURE = A0;
const uint8_t PIN_WATER_LEVEL = 2;
const uint8_t PIN_ONE_WIRE = 3;
const uint8_t PIN_PUMP = 5;
const uint8_t PIN_FAN = 6;
const uint8_t PIN_LED_PWM = 9;

// Calibrate with your own capacitive soil moisture sensor.
const int SOIL_ADC_DRY = 820;
const int SOIL_ADC_WET = 360;

const unsigned long SENSOR_INTERVAL_MS = 5000;
const unsigned long PI_TIMEOUT_MS = 120000;
const unsigned long MAX_PUMP_RUN_MS = 10000;
const unsigned long MIN_PUMP_REST_MS = 6UL * 60UL * 60UL * 1000UL;
const unsigned long DAILY_RESET_MS = 24UL * 60UL * 60UL * 1000UL;
const unsigned long DAILY_MAX_PUMP_MS = 60000;
const uint8_t DAILY_MAX_WATERINGS = 8;

Adafruit_SHT31 sht31 = Adafruit_SHT31();
BH1750 lightMeter;
OneWire oneWire(PIN_ONE_WIRE);
DallasTemperature ds18b20(&oneWire);

struct ActuatorState {
  bool pump = false;
  bool fan = false;
  uint8_t ledPwm = 0;
  unsigned long pumpStartedAt = 0;
  unsigned long pumpStopAt = 0;
  unsigned long lastPumpStopAt = 0;
  unsigned long dailyPumpMs = 0;
  uint8_t dailyWaterings = 0;
  unsigned long dayStartedAt = 0;
};

ActuatorState state;
unsigned long lastSensorAt = 0;
unsigned long lastPiSeenAt = 0;
bool shtReady = false;
bool lightReady = false;

void setup() {
  pinMode(PIN_WATER_LEVEL, INPUT_PULLUP);
  pinMode(PIN_PUMP, OUTPUT);
  pinMode(PIN_FAN, OUTPUT);
  pinMode(PIN_LED_PWM, OUTPUT);

  digitalWrite(PIN_PUMP, LOW);
  digitalWrite(PIN_FAN, LOW);
  analogWrite(PIN_LED_PWM, 0);

  Serial.begin(115200);
  Wire.begin();
  shtReady = sht31.begin(0x44);
  lightReady = lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE);
  ds18b20.begin();

  state.dayStartedAt = millis();
  lastPiSeenAt = millis();
}

void loop() {
  unsigned long now = millis();
  readSerialCommands();
  enforceSafety(now);

  if (now - lastSensorAt >= SENSOR_INTERVAL_MS) {
    lastSensorAt = now;
    publishSensorReading(now);
  }

  if (now - state.dayStartedAt >= DAILY_RESET_MS) {
    state.dayStartedAt = now;
    state.dailyPumpMs = 0;
    state.dailyWaterings = 0;
  }
}

float soilMoisturePercent() {
  int raw = analogRead(PIN_SOIL_MOISTURE);
  float pct = 100.0f * (SOIL_ADC_DRY - raw) / (SOIL_ADC_DRY - SOIL_ADC_WET);
  if (pct < 0) pct = 0;
  if (pct > 100) pct = 100;
  return pct;
}

const char* waterLevelState() {
  // INPUT_PULLUP: LOW means float switch closed/OK in this reference wiring.
  return digitalRead(PIN_WATER_LEVEL) == LOW ? "ok" : "low";
}

void publishSensorReading(unsigned long now) {
  float airTemp = shtReady ? sht31.readTemperature() : NAN;
  float airHumidity = shtReady ? sht31.readHumidity() : NAN;
  ds18b20.requestTemperatures();
  float soilTemp = ds18b20.getTempCByIndex(0);
  float lux = lightReady ? lightMeter.readLightLevel() : NAN;

  StaticJsonDocument<384> doc;
  doc["type"] = "sensor_reading";
  doc["timestamp_ms"] = now;
  if (!isnan(airTemp)) doc["air_temp"] = airTemp;
  if (!isnan(airHumidity)) doc["air_humidity"] = airHumidity;
  doc["soil_moisture"] = soilMoisturePercent();
  if (soilTemp > -100 && soilTemp < 100) doc["soil_temp"] = soilTemp;
  if (!isnan(lux)) doc["light_lux"] = lux;
  doc["water_level"] = waterLevelState();
  doc["pump"] = state.pump;
  doc["fan"] = state.fan;
  doc["led_pwm"] = state.ledPwm;

  serializeJson(doc, Serial);
  Serial.println();
}

void readSerialCommands() {
  static String line;
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n') {
      line.trim();
      if (line.length() > 0) {
        lastPiSeenAt = millis();
        handleCommand(line);
      }
      line = "";
    } else if (line.length() < 512) {
      line += c;
    } else {
      line = "";
    }
  }
}

void handleCommand(const String& line) {
  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, line);
  if (err || doc["type"] != "command") {
    sendAck(doc["command_id"] | "unknown", "rejected", "invalid command json");
    return;
  }

  const char* commandId = doc["command_id"] | "unknown";
  const char* actuator = doc["actuator"] | "";
  const char* action = doc["action"] | "";
  unsigned long durationMs = doc["duration_ms"] | 0;
  int value = doc["value"] | 0;

  if (strcmp(actuator, "pump") == 0) {
    handlePumpCommand(commandId, action, durationMs);
  } else if (strcmp(actuator, "fan") == 0) {
    digitalWrite(PIN_FAN, strcmp(action, "on") == 0 ? HIGH : LOW);
    state.fan = strcmp(action, "on") == 0;
    sendAck(commandId, "accepted", state.fan ? "fan on" : "fan off");
  } else if (strcmp(actuator, "light") == 0) {
    if (strcmp(action, "off") == 0) value = 0;
    if (value < 0) value = 0;
    if (value > 255) value = 255;
    state.ledPwm = value;
    analogWrite(PIN_LED_PWM, state.ledPwm);
    sendAck(commandId, "accepted", "light updated");
  } else {
    sendAck(commandId, "rejected", "unknown actuator");
  }
}

void handlePumpCommand(const char* commandId, const char* action, unsigned long durationMs) {
  unsigned long now = millis();

  if (strcmp(action, "off") == 0) {
    stopPump(now);
    sendAck(commandId, "accepted", "pump stopped");
    return;
  }

  if (strcmp(waterLevelState(), "ok") != 0) {
    sendAck(commandId, "rejected", "water level low");
    return;
  }
  if (durationMs == 0 || durationMs > MAX_PUMP_RUN_MS) {
    sendAck(commandId, "rejected", "duration exceeds max pump run");
    return;
  }
  if (state.dailyWaterings >= DAILY_MAX_WATERINGS || state.dailyPumpMs + durationMs > DAILY_MAX_PUMP_MS) {
    sendAck(commandId, "rejected", "daily pump limit reached");
    return;
  }
  if (state.lastPumpStopAt > 0 && now - state.lastPumpStopAt < MIN_PUMP_REST_MS) {
    sendAck(commandId, "rejected", "pump rest interval active");
    return;
  }

  state.pump = true;
  state.pumpStartedAt = now;
  state.pumpStopAt = now + durationMs;
  state.dailyWaterings += 1;
  digitalWrite(PIN_PUMP, HIGH);
  sendAck(commandId, "accepted", "pump started");
}

void enforceSafety(unsigned long now) {
  if (state.pump && strcmp(waterLevelState(), "ok") != 0) {
    stopPump(now);
    sendSafetyEvent("pump stopped: water level low");
  }

  if (state.pump && (now - state.pumpStartedAt >= MAX_PUMP_RUN_MS || now >= state.pumpStopAt)) {
    stopPump(now);
  }

  if (now - lastPiSeenAt > PI_TIMEOUT_MS) {
    if (state.pump) {
      stopPump(now);
      sendSafetyEvent("pump stopped: pi timeout");
    }
    state.ledPwm = 0;
    analogWrite(PIN_LED_PWM, 0);
  }
}

void stopPump(unsigned long now) {
  if (state.pump) {
    unsigned long ranFor = now - state.pumpStartedAt;
    state.dailyPumpMs += ranFor;
  }
  state.pump = false;
  state.pumpStartedAt = 0;
  state.pumpStopAt = 0;
  state.lastPumpStopAt = now;
  digitalWrite(PIN_PUMP, LOW);
}

void sendAck(const char* commandId, const char* status, const char* message) {
  StaticJsonDocument<192> doc;
  doc["type"] = "command_ack";
  doc["command_id"] = commandId;
  doc["status"] = status;
  doc["message"] = message;
  serializeJson(doc, Serial);
  Serial.println();
}

void sendSafetyEvent(const char* message) {
  StaticJsonDocument<192> doc;
  doc["type"] = "safety_event";
  doc["timestamp_ms"] = millis();
  doc["level"] = "warning";
  doc["message"] = message;
  serializeJson(doc, Serial);
  Serial.println();
}
