# Arduino Smart Farm Circuit Design

방울토마토 스마트팜 Arduino 회로 상세 설계서입니다. 현재 펌웨어 [arduino/smartfarm_controller/smartfarm_controller.ino](/Users/sehan/Documents/Projects/Arduino%20Pi%20Smart%20farm/arduino/smartfarm_controller/smartfarm_controller.ino) 기준입니다.

## 1. 설계 목표

- Arduino: 센서 수집, 펌프/팬/LED 제어, 최후 안전 제어 담당
- Raspberry Pi: USB Serial로 명령/데이터 교환
- 센서 전원: Arduino 5V 또는 3.3V 레일 사용
- 펌프/팬/LED 전원: Arduino에서 직접 공급 금지, 별도 전원 사용
- 모든 액추에이터: MOSFET 또는 릴레이 모듈로 제어
- 펌프 안전: 수위 낮음, 과동작, Pi 연결 끊김이면 Arduino가 자체 차단

## 2. 전체 회로 블록

```text
Raspberry Pi
  USB
   |
Arduino Uno/Nano/Mega
   |
   |-- I2C: SHT31 + BH1750
   |-- A0: Capacitive soil moisture
   |-- D3: DS18B20 1-Wire
   |-- D2: Water level switch
   |-- D5: Pump driver input
   |-- D6: Fan driver input
   |-- D9: LED MOSFET PWM input

External power rails
   |
   |-- Pump supply, e.g. 5V/12V
   |-- Fan supply, e.g. 5V/12V
   |-- LED supply, LED spec dependent
```

## 3. 기준 부품

| 구분 | 권장 부품 | 비고 |
| --- | --- | --- |
| MCU | Arduino Uno 또는 Nano | Uno 기준 핀 설명. Nano도 거의 동일 |
| 공기 온습도 | SHT31 module | I2C, 3.3V/5V 모듈 확인 |
| 토양 수분 | Capacitive soil moisture sensor v1.2 | Analog 출력 |
| 토양 온도 | Waterproof DS18B20 | 1-Wire, 4.7k pull-up 필요 |
| 조도 | BH1750 module | I2C |
| 수위 | Float switch 또는 digital water level switch | `LOW = ok`, `HIGH = low` 기준 |
| 펌프 | DC submersible pump | 별도 전원 필수 |
| 팬 | DC fan | 별도 전원 권장 |
| LED | Grow LED strip/module | MOSFET PWM 제어 |
| 펌프/팬 드라이버 | Logic-level N-MOSFET 또는 relay module | DC 펌프/팬이면 MOSFET 권장 |
| LED 드라이버 | Logic-level N-MOSFET | IRLZ44N, AO3400, FQP30N06L 등 |
| 보호 소자 | Flyback diode, fuse, terminal block | 모터/릴레이 보호 |

## 4. Arduino 핀맵

| Arduino 핀 | 연결 대상 | 방향 | 펌웨어 상수 | 설명 |
| --- | --- | --- | --- | --- |
| `5V` | 5V 센서 VCC | Power | - | 센서 모듈 전원 |
| `3.3V` | 3.3V 전용 센서 VCC | Power | - | 모듈 스펙 확인 후 사용 |
| `GND` | 모든 센서 GND, 드라이버 GND | Ground | - | 공통 기준점 |
| `A0` | 토양 수분 AO | Input | `PIN_SOIL_MOISTURE` | ADC 읽기 |
| `D2` | 수위 스위치 | Input pull-up | `PIN_WATER_LEVEL` | `LOW = ok`, `HIGH = low` |
| `D3` | DS18B20 DATA | Input/output | `PIN_ONE_WIRE` | 4.7k pull-up |
| `D5` | 펌프 MOSFET/릴레이 IN | Output | `PIN_PUMP` | HIGH = pump on |
| `D6` | 팬 MOSFET/릴레이 IN | Output | `PIN_FAN` | HIGH = fan on |
| `D9` | LED MOSFET gate | PWM output | `PIN_LED_PWM` | 0-255 PWM |
| `A4` Uno/Nano | I2C SDA | I2C | `Wire` | SHT31, BH1750 |
| `A5` Uno/Nano | I2C SCL | I2C | `Wire` | SHT31, BH1750 |
| USB | Raspberry Pi | Serial | `Serial` | 115200 baud |

Mega 사용 시 I2C 핀은 `SDA=20`, `SCL=21`입니다.

## 5. 전원 설계

### 5.1 최소 전원 구조

```text
Raspberry Pi USB port
  |
  |-- USB cable
      |
    Arduino
      |
      |-- 5V sensors only

External DC adapter
  |
  |-- Pump +
  |-- Fan +
  |-- LED +
```

Arduino USB 전원으로 센서만 구동하세요. 펌프/팬/LED 전류를 Arduino 5V 핀에서 가져오면 안 됩니다.

### 5.2 공통 GND

MOSFET 제어를 쓰면 Arduino GND와 외부 전원 GND를 반드시 공통으로 묶어야 합니다.

```text
Arduino GND ---- External power GND
```

릴레이 모듈 중 opto-isolated 타입은 모듈 스펙에 따라 GND 분리 가능하지만, 초반 MVP는 공통 GND 구성이 디버깅 쉽습니다.

### 5.3 전원 용량 예시

| 부하 | 예시 전압 | 예시 전류 | 전원 권장 |
| --- | --- | --- | --- |
| Arduino + sensors | 5V | 100-300mA | Pi USB 또는 별도 5V |
| 소형 펌프 | 5V/12V | 300mA-2A | 정격 전류 2배 여유 |
| DC fan | 5V/12V | 100mA-500mA | 정격 전류 2배 여유 |
| LED strip | 5V/12V | 500mA-수 A | LED 소비전류 기준 |

펌프 기동 전류는 정격보다 큽니다. 전원은 여유 있게 잡으세요.

## 6. 센서 회로

### 6.1 SHT31 공기 온습도 센서

| SHT31 | Arduino Uno/Nano |
| --- | --- |
| `VCC` | `5V` 또는 `3.3V` |
| `GND` | `GND` |
| `SDA` | `A4` |
| `SCL` | `A5` |

주의:

- 보드가 5V tolerant인지 확인하세요.
- 대부분 breakout module은 pull-up 포함. 두 I2C 모듈 pull-up이 모두 있으면 보통 문제 없음.
- 직사광/LED 직격 피하고 통풍 위치에 설치.

펌웨어:

```cpp
shtReady = sht31.begin(0x44);
```

주소 충돌 발생 시 SHT31 보드의 address solder jumper 확인.

### 6.2 BH1750 조도 센서

| BH1750 | Arduino Uno/Nano |
| --- | --- |
| `VCC` | `5V` 또는 `3.3V` |
| `GND` | `GND` |
| `SDA` | `A4` |
| `SCL` | `A5` |

SHT31과 같은 I2C 버스 공유.

```text
A4 SDA ---- SHT31 SDA ---- BH1750 SDA
A5 SCL ---- SHT31 SCL ---- BH1750 SCL
GND    ---- SHT31 GND ---- BH1750 GND
VCC    ---- SHT31 VCC ---- BH1750 VCC
```

주의:

- 잎 높이 근처, LED/햇빛 대표 위치에 설치.
- 물 튐 방지. 투명 커버 사용 시 lux 값 감소 보정 필요.

### 6.3 Capacitive Soil Moisture Sensor

| Soil moisture sensor | Arduino |
| --- | --- |
| `VCC` | `5V` 또는 `3.3V` |
| `GND` | `GND` |
| `AOUT` | `A0` |

권장:

- Capacitive 타입 사용. 저항식 부식 빠름.
- 케이블 길면 신호 흔들림. 가능하면 30-50cm 이하.
- `AOUT` 옆에 0.1uF ceramic capacitor를 GND로 붙이면 노이즈 감소.

펌웨어 보정값:

```cpp
const int SOIL_ADC_DRY = 820;
const int SOIL_ADC_WET = 360;
```

보정 절차:

1. 센서 공기 중 또는 완전 마른 흙에 꽂고 raw ADC 측정.
2. 충분히 젖은 흙에 꽂고 raw ADC 측정.
3. `SOIL_ADC_DRY`, `SOIL_ADC_WET` 수정.
4. 실제 흙에서 1-2일 로그 보고 기준값 재조정.

### 6.4 DS18B20 토양 온도 센서

| DS18B20 | Arduino |
| --- | --- |
| Red `VDD` | `5V` |
| Black `GND` | `GND` |
| Yellow/White `DATA` | `D3` |

필수:

```text
4.7kΩ resistor between DATA and 5V
```

배선:

```text
5V ---- DS18B20 VDD
GND --- DS18B20 GND
D3 ---- DS18B20 DATA
5V --[4.7k]-- D3
```

주의:

- 방수 프로브라도 케이블 연결부는 실리콘/수축튜브 처리.
- 값 `-127 C` 또는 `85 C` 고정이면 배선/풀업/센서 초기화 문제.

### 6.5 수위 센서

현재 펌웨어 기준:

```cpp
pinMode(PIN_WATER_LEVEL, INPUT_PULLUP);
return digitalRead(PIN_WATER_LEVEL) == LOW ? "ok" : "low";
```

즉 회로는 `LOW = 물 충분`, `HIGH = 물 부족` 기준입니다.

Float switch 배선 예:

| Float switch | Arduino |
| --- | --- |
| 한쪽 선 | `D2` |
| 다른 선 | `GND` |

동작:

- 스위치 닫힘: `D2`가 GND와 연결 -> `LOW` -> `ok`
- 스위치 열림: internal pull-up -> `HIGH` -> `low`

주의:

- 실제 float 방향에 따라 닫힘/열림이 반대일 수 있음. 물통에 넣고 Serial 출력으로 확인.
- 펌프 흡입구보다 높은 위치에 설치. 물이 거의 없기 전에 펌프 차단.
- 수위 센서는 안전 최우선. 접촉 불량이면 `low`가 되도록 구성하는 쪽이 안전.

## 7. 액추에이터 회로

### 7.1 MOSFET 방식 권장 회로

DC 펌프, DC 팬, LED 모두 N-channel logic-level MOSFET low-side switching 권장.

공통 회로:

```text
External +V ---- Load + 
Load - --------- MOSFET Drain
MOSFET Source -- External GND
Arduino GND ---- External GND
Arduino pin ----[100Ω]---- MOSFET Gate
Gate -----------[100kΩ]--- GND
```

부품:

- Logic-level N-MOSFET: `IRLZ44N`, `FQP30N06L`, `AO3400` 등
- Gate resistor: 100Ω-220Ω
- Gate pulldown: 47kΩ-100kΩ
- 모터 부하 flyback diode: 1N5819, 1N4007, SS14 등

### 7.2 펌프 회로

```text
Pump power +  ---- Pump +
Pump -        ---- MOSFET Drain
MOSFET Source ---- Pump power GND
Arduino GND   ---- Pump power GND
D5            ----[100Ω]---- MOSFET Gate
Gate          ----[100kΩ]--- GND

Flyback diode:
diode cathode(stripe) -> Pump +
diode anode           -> Pump -
```

펌웨어:

```cpp
const uint8_t PIN_PUMP = 5;
digitalWrite(PIN_PUMP, HIGH); // pump on
```

안전:

- 펌프 전원 라인에 fuse 권장.
- 물통 밖 공회전 금지.
- 테스트 때 물 없는 상태로 1초 이상 돌리지 마세요.
- 수위 센서 `low`면 펌웨어가 명령 거절.

### 7.3 팬 회로

펌프와 같은 MOSFET 구조.

```text
Fan power +  ---- Fan +
Fan -        ---- MOSFET Drain
MOSFET Source ---- Fan power GND
Arduino GND  ---- Fan power GND
D6           ----[100Ω]---- MOSFET Gate
Gate         ----[100kΩ]--- GND
Flyback diode across fan
```

펌웨어:

```cpp
const uint8_t PIN_FAN = 6;
```

팬이 4-wire PC fan이면:

- `+12V`, `GND`는 외부 전원
- PWM pin은 별도 25kHz 제어가 필요할 수 있음
- MVP는 2-wire DC fan + MOSFET on/off가 단순

### 7.4 LED 성장등 PWM 회로

```text
LED power +  ---- LED +
LED -        ---- MOSFET Drain
MOSFET Source ---- LED power GND
Arduino GND  ---- LED power GND
D9           ----[100Ω]---- MOSFET Gate
Gate         ----[100kΩ]--- GND
```

펌웨어:

```cpp
const uint8_t PIN_LED_PWM = 9;
analogWrite(PIN_LED_PWM, value); // 0-255
```

주의:

- LED 정격 전압/전류 확인.
- 고출력 LED는 정전류 드라이버 필요. MOSFET PWM은 LED strip류에 적합.
- LED 전류 크면 MOSFET 방열판 필요.

## 8. 릴레이 모듈 사용 시 대안

펌프/팬을 릴레이 모듈로 제어 가능.

| Relay module | Arduino |
| --- | --- |
| `VCC` | `5V` |
| `GND` | `GND` |
| `IN1` pump | `D5` |
| `IN2` fan | `D6` |

부하 배선:

```text
Power + ---- Relay COM
Relay NO --- Load +
Load - ----- Power -
```

주의:

- 릴레이 모듈이 active LOW인지 active HIGH인지 확인. 현재 펌웨어는 `HIGH = on`.
- active LOW 모듈이면 펌웨어 논리 반전 필요.
- 릴레이는 PWM 불가. LED 밝기 제어에는 부적합.
- DC 모터 부하에는 relay contact 보호용 diode/snubber 고려.

## 9. I2C 버스 설계

현재 I2C 장치:

- SHT31: 보통 `0x44`
- BH1750: 보통 `0x23` 또는 `0x5C`

연결:

```text
Arduino A4 SDA ---- SHT31 SDA ---- BH1750 SDA
Arduino A5 SCL ---- SHT31 SCL ---- BH1750 SCL
Arduino GND    ---- SHT31 GND ---- BH1750 GND
Arduino 5V/3.3V---- SHT31 VCC ---- BH1750 VCC
```

주의:

- I2C 케이블 길이 짧게 유지. 30cm 이하 권장.
- 긴 케이블 필요하면 pull-up 저항 조정, twisted pair, I2C extender 고려.
- 센서 모듈마다 pull-up 포함. 너무 많은 pull-up 병렬이면 버스 과부하 가능.

## 10. 선택 센서 확장

현재 펌웨어는 pH/EC/CO2 필드를 백엔드 DB에 준비했지만 Arduino 코드에는 아직 실제 읽기 구현이 없습니다.

### 10.1 pH sensor

권장:

- Analog pH module이면 `A1` 사용 후보
- BNC probe + interface board
- pH 4.00, 7.00 보정액으로 2점 보정

주의:

- pH probe는 건조 금지.
- 온도 보상 없으면 값 흔들림.
- 초기 MVP는 자동 제어 금지, 기록/관찰만.

### 10.2 EC sensor

권장:

- Analog EC module이면 `A2` 사용 후보
- 온도 보상 필요
- 표준용액으로 보정

주의:

- pH/EC analog 센서 동시 사용 시 전기적 간섭 가능.
- 측정 시점을 나누거나 isolated interface 고려.

### 10.3 MH-Z19B CO2 sensor

권장:

- UART 사용
- Uno/Nano면 SoftwareSerial 후보: `D10` RX, `D11` TX
- Mega면 Serial1 권장

주의:

- 5V 전원 필요, 전류 여유 확보.
- 예열 시간 필요.
- 자동 보정(ABC) 환경에 따라 끄는 것이 나을 수 있음.

## 11. 배선 순서

### 11.1 센서만 먼저 연결

1. Arduino와 Pi는 아직 분리. Arduino를 PC에 USB 연결.
2. SHT31, BH1750 I2C 연결.
3. DS18B20 + 4.7k pull-up 연결.
4. 토양 수분 센서 `A0` 연결.
5. 수위 스위치 `D2-GND` 연결.
6. Arduino Serial Monitor 115200 baud 확인.
7. JSON Lines가 5초마다 출력되는지 확인.

예상 출력:

```json
{"type":"sensor_reading","timestamp_ms":12345,"air_temp":24.8,"air_humidity":62.1,"soil_moisture":37.4,"soil_temp":22.2,"light_lux":12450,"water_level":"ok","pump":false,"fan":false,"led_pwm":0}
```

### 11.2 액추에이터 드라이버만 테스트

1. 펌프 대신 LED + resistor 또는 multimeter로 D5 출력 확인.
2. 팬 대신 LED + resistor 또는 multimeter로 D6 출력 확인.
3. LED MOSFET에는 작은 LED strip부터 테스트.
4. 릴레이/MOSFET 발열 확인.
5. 전원 GND 공통 확인.

### 11.3 실제 부하 연결

1. 외부 전원 OFF.
2. 펌프/팬/LED 부하 연결.
3. fuse와 flyback diode 방향 확인.
4. 외부 전원 ON.
5. 짧은 수동 명령으로 1초-5초 테스트.
6. 물탱크 낮은 수위 상태에서 펌프 명령 거절되는지 확인.

## 12. Raspberry Pi 연결

Arduino USB를 Pi에 연결하면 보통:

```bash
/dev/ttyACM0
```

확인:

```bash
ls /dev/ttyACM*
ls /dev/ttyUSB*
```

서버 실행:

```bash
cd ~/Arduino-Pi-Smart-Farm/raspberry_pi
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

기본 포트는 `/dev/ttyACM0`입니다. 다른 포트면:

```bash
SERIAL_PORT=/dev/ttyUSB0 uvicorn app.main:app --host 0.0.0.0 --port 8000
```

웹 대시보드에서 확인:

- Arduino 포트: `/dev/ttyACM0`
- 장치 감지: `감지됨`
- Serial 연결: `열림`
- 센서 데이터: `수신됨 ...`

## 13. 권장 배선 색상

| 신호 | 색상 |
| --- | --- |
| 5V | Red |
| 3.3V | Orange |
| GND | Black |
| I2C SDA | Blue |
| I2C SCL | Yellow |
| 1-Wire DATA | White |
| Analog signal | Green |
| Actuator control | Purple |
| External power + | Red thick wire |
| External power - | Black thick wire |

액추에이터 전류가 큰 곳은 breadboard 쓰지 마세요. 터미널 블록, 납땜, WAGO, screw terminal 권장.

## 14. 안전 체크리스트

- [ ] Arduino GND와 외부 전원 GND 공통.
- [ ] 펌프/팬/LED 전원은 Arduino 5V에서 직접 공급하지 않음.
- [ ] 펌프/팬에 flyback diode 설치.
- [ ] MOSFET gate pulldown 설치.
- [ ] 수위 센서 뽑힘/단선 시 펌프가 켜지지 않는 방향 확인.
- [ ] 펌프 최대 동작 시간 `MAX_PUMP_RUN_MS` 확인.
- [ ] 하루 펌프 제한 `DAILY_MAX_PUMP_MS`, `DAILY_MAX_WATERINGS` 확인.
- [ ] 젖은 환경 배선 방수 처리.
- [ ] 220V AC 직접 제어 금지. 필요 시 검증된 릴레이 박스/전문가 도움.
- [ ] 모든 테스트는 펌프 전원 OFF 상태에서 배선 먼저 확인.

## 15. MVP 권장 제작 순서

1. Arduino + 센서만 구성.
2. Serial JSON 출력 확인.
3. Raspberry Pi 대시보드에서 센서 수신 확인.
4. MOSFET 드라이버 보드 구성.
5. 펌프 대신 테스트 LED로 D5 제어 확인.
6. 팬 대신 테스트 LED로 D6 제어 확인.
7. LED PWM 작은 부하로 확인.
8. 실제 펌프/팬/LED 연결.
9. 수위 low 상태에서 펌프 lockout 확인.
10. 24시간 센서 로그 안정성 확인.

## 16. 흔한 문제

| 증상 | 원인 후보 | 확인/해결 |
| --- | --- | --- |
| SHT31 값 없음 | I2C 배선, 주소 문제 | SDA/SCL, `0x44` 확인 |
| BH1750 값 없음 | I2C 주소/전원 문제 | I2C scanner 실행 |
| DS18B20 `-127 C` | DATA 단선, pull-up 없음 | 4.7k 확인 |
| 토양수분 0/100 고정 | 보정값 틀림, AOUT 오배선 | raw ADC 출력 확인 |
| 수위가 반대로 표시 | float switch 방향 반대 | 스위치 뒤집거나 코드 논리 변경 |
| 펌프 안 켜짐 | GND 미공통, MOSFET gate 문제 | GND, gate voltage 확인 |
| 펌프 항상 켜짐 | MOSFET 배선 오류, gate pulldown 없음 | drain/source 방향 확인 |
| Pi에서 Arduino 안 보임 | USB 케이블 충전 전용 | 데이터 USB 케이블 사용 |
| `/dev/ttyACM0` 없음 | 보드/드라이버/케이블 문제 | `dmesg`, `lsusb` 확인 |

## 17. ASCII 회로 요약

```text
                         Raspberry Pi
                              |
                         USB Serial
                              |
                           Arduino
      +-----------------------+------------------------+
      |                       |                        |
   I2C A4/A5               Sensors                 Outputs
      |                       |                        |
 SHT31 + BH1750       Soil A0, DS18B20 D3       D5/D6/D9
                              |                        |
                       Water switch D2          MOSFET gates
                                                       |
External supply + ---- Pump/Fan/LED +                  |
Pump/Fan/LED -  ---- MOSFET Drain                      |
MOSFET Source  ---- External supply GND ---- Arduino GND
```

## 18. 펌웨어와 회로가 맞아야 하는 값

| 회로 결정 | 펌웨어 위치 |
| --- | --- |
| 토양 수분 핀 `A0` | `PIN_SOIL_MOISTURE` |
| 수위 핀 `D2` | `PIN_WATER_LEVEL` |
| DS18B20 핀 `D3` | `PIN_ONE_WIRE` |
| 펌프 제어 핀 `D5` | `PIN_PUMP` |
| 팬 제어 핀 `D6` | `PIN_FAN` |
| LED PWM 핀 `D9` | `PIN_LED_PWM` |
| 토양 건조 ADC | `SOIL_ADC_DRY` |
| 토양 젖음 ADC | `SOIL_ADC_WET` |
| 펌프 1회 최대 | `MAX_PUMP_RUN_MS` |
| Pi timeout | `PI_TIMEOUT_MS` |

회로 변경하면 펌웨어 상수도 같이 바꾸세요.
