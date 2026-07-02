# Wokwi 시뮬레이션 (Phase 1 하드웨어 적합성 검증용)

부품 구매 전에 `smartfarm_controller.ino`가 후보 센서/액추에이터 전체와 배선/신호 레벨에서 문제가 없는지 [Wokwi](https://wokwi.com)로 먼저 확인하기 위한 프로젝트입니다.

## 무엇을 검증할 수 있는가 / 없는가

검증 가능:
- 핀 배치가 실제로 충돌 없이 동작하는지 (Analog 1, Digital 4, I2C 2, PWM 1)
- `safety_rules`/펌프 lockout, `MAX_PUMP_RUN_MS` 등 안전 로직이 실제로 의도대로 동작하는지 (시리얼 모니터 로그로 확인)
- 시리얼 JSON Lines 프로토콜이 스펙대로 출력되는지 (SHT31/BH1750 값은 시뮬레이션 스텁 값)

검증 불가 (전기적 시뮬레이션 아님):
- 펌프/팬 실제 전류, 회전력, MOSFET 발열
- 센서 정확도, 노이즈, 실제 캘리브레이션 값
- SHT31(`0x44`)/BH1750(`0x23`) 실제 I2C 통신 및 두 주소 동시 응답 여부 — Wokwi에 두 칩의 공식/커뮤니티 모델이 없어서 시뮬레이션 불가. 주소값(`0x44` vs `0x23`)이 겹치지 않는 것은 코드 리뷰로 확인 완료. 실제 I2C 동작은 부품 도착 후 실기로 검증하세요.
- 이 부분은 이미 정리된 [하드웨어 체크리스트](../../README.md)와 `ARDUINO_CIRCUIT_DESIGN.md`의 전원 설계 표로 별도 계산하세요.

## 부품 매핑

| 실제 부품 | Wokwi 부품 | 비고 |
| --- | --- | --- |
| Arduino Uno | `wokwi-arduino-uno` | |
| 브레드보드 (아래쪽) | `wokwi-breadboard` (`bb1`) | 하단 그룹(토양 수분) 전원 배분. 아래 "배선 구조" 참고 |
| 브레드보드 (위쪽) | `wokwi-breadboard` (`bb2`) | 상단 그룹(릴레이/DS18B20/수위 센서) 전원 배분 |
| 토양 수분 센서 (Analog) | `wokwi-potentiometer` | ADC 0~1023 신호 특성이 동일해서 로직 검증용 대체재로 사용 |
| 수위 센서 (Digital, `INPUT_PULLUP`) | `wokwi-pushbutton` | 안 누르면 HIGH(=low), 누르면 LOW(=ok). 실제 float switch와 논리는 동일 |
| DS18B20 | `wokwi-ds18b20` + 4.7kΩ pull-up | 회로 가이드와 동일하게 pull-up 저항 포함 |
| 펌프 릴레이 | `wokwi-relay-module` (D5) | |
| 팬 릴레이 | `wokwi-relay-module` (D6) | |
| LED 성장등 (PWM) | LED + 저항 (D9) | 실제 회로는 MOSFET 구동이지만, PWM 신호/밝기 검증 목적이라 LED 직결로 충분 |
| SHT31 | 없음 (펌웨어 스텁으로 대체) | 아래 참고 |
| BH1750 | 없음 (펌웨어 스텁으로 대체) | 아래 참고 |

## 배선 구조 (브레드보드 2개 + 상/하 분리 배치)

**v1(전원 레일만 도입)의 문제**: 브레드보드 1개로 전원만 몰아줬지만, 부품들이 여전히 Arduino 주변에 아무렇게나 배치되어 있어서 신호선이 보드 몸통 위를 가로지르며 다른 배선과 겹쳤습니다 (특히 위쪽 핀(D2/D3/D5/D6/D9)에 연결된 부품이 보드 아래쪽/옆에 있으니 배선이 보드를 대각선으로 가로지름).

**v2(지금)**: Arduino Uno의 실제 핀 위치를 기준으로 부품을 완전히 재배치해서, 어떤 배선도 보드 몸통 위를 지나가지 않도록 했습니다.

- Uno는 **디지털 핀(0~13)이 위쪽 헤더, 아날로그 핀(A0~A5)과 전원 핀(5V/GND/Vin)이 아래쪽 헤더**에 있습니다 (GND는 예외적으로 위/아래 모두 있음 — `GND.1`은 13번 핀 옆 위쪽, `GND.2`/`GND.3`은 아래쪽). [공식 참고](https://docs.wokwi.com/parts/wokwi-arduino-uno#pin-names)
- 그래서 부품도 신호 핀 위치에 맞춰 나눴습니다:
  - **아래쪽 그룹** (A0 핀 근처): 토양 수분 센서 + `bb1`. `uno:5V`/`uno:GND.2` → `bb1` 레일 → 토양 수분 센서 VCC/GND.
  - **위쪽 그룹** (D2/D3/D5/D6/D9 핀 근처): 펌프/팬 릴레이, DS18B20+pull-up, 수위 센서, LED+저항 + `bb2`. GND는 위쪽에도 `GND.1`이 있어서 `uno:GND.1` → `bb2` 레일로 바로 공급.
  - LED는 GND만 필요해서(애노드는 저항을 거쳐 신호 핀) `bb2`를 거치지 않고 `uno:GND.1`에 바로 연결 — 배선 1개 더 절약.
- **유일하게 보드를 "우회"하는 배선**은 `uno:5V → bb2:bp.1` 하나뿐입니다. 5V는 아래쪽에만 있는데 위쪽 그룹도 5V가 필요해서, `diagram.json`의 [wire placement mini-language](https://docs.wokwi.com/diagram-format#wire-placement-mini-language)(`v`/`h` 꺾임 지정)로 다른 어떤 부품과도 겹치지 않는 먼 오른쪽(x=900)까지 나간 뒤 그 지점에서만 수직으로 오르내리도록 지정했습니다.
- 신호선(아날로그/디지털/PWM/1-Wire)은 여전히 Arduino 핀과 부품 사이 직결입니다. 부품이 이제 자기 핀과 같은 쪽(위/아래)에 있어서 이 직결 배선도 짧고 곧게 나옵니다.

## v3: 겹침 수정 + 배선 색상으로 구분

v2를 실제로 열어보니 두 가지 문제가 더 있었습니다.

1. **`bb2`(위쪽 브레드보드)가 Uno와 겹침**: v2에서 Uno와 `bb2` 사이 간격을 100 유닛만 뒀는데, 실제 브레드보드 렌더링 높이가 그보다 커서 Uno의 위쪽 헤더 부분을 덮어버렸습니다. → Uno-`bb2` 간격을 340 유닛으로, `bb2`-상단 부품 그룹 간격을 250 유닛으로 크게 늘렸습니다. LED 그룹은 아예 `bb2`의 왼쪽 바깥(수평으로 완전히 분리)으로 옮겨서 세로 위치가 겹쳐도 부품끼리 겹칠 일이 없게 했습니다.
2. **같은 색 배선이 여러 개 겹쳐서 추적 불가**: 신호선을 전부 초록색, GND선을 전부 검정색으로 통일했더니, 여러 배선이 한 구간(특히 Uno 위쪽 배선이 모이는 구간)에 몰릴 때 어떤 초록선이 어떤 부품 것인지 구분이 안 됐습니다. → **부품 하나당 색 하나**로 바꿨습니다: 그 부품에 연결된 신호선/VCC선/GND선을 전부 같은 색으로 칠해서, 색만 보고 "이 색 선은 전부 이 부품 것"이라고 바로 알아볼 수 있게 했습니다.
   - 토양 수분 센서: 주황(`orange`) / LED: 자홍(`magenta`) / 팬 릴레이: 파랑(`blue`) / 펌프 릴레이: 보라(`purple`) / DS18B20+pull-up: 노랑(`yellow`, 기존 1-Wire 관례 유지) / 수위 센서: 청록(`cyan`)
   - Uno ↔ 브레드보드 "간선"(`5V`/`GND` 각 2줄)만 빨강/검정 관례를 유지 — 브레드보드당 각 1개씩만 있어서 헷갈릴 일이 없습니다.

> 여전히 정확한 부품 크기를 실측하지 못하고 추정치로 배치한 것이라, 이번에도 약간의 여백/겹침 오차가 있을 수 있습니다. 그럴 땐 스크린샷을 다시 보내주시면 계속 조정하거나, VS Code에서 직접 드래그로 옮기셔도 배선은 그대로 유지됩니다.

> **참고**: 이 좌표는 Uno/브레드보드 부품의 대략적인 렌더링 크기를 추정해서 계산한 값이라, 실제로 열어보면 부품 간 간격이 약간 좁거나 넓을 수 있습니다. 전기적 연결(어떤 핀과 어떤 핀이 연결되는지)은 좌표와 무관하게 항상 올바르며, 위치가 마음에 안 들면 VS Code에서 부품을 마우스로 드래그해서 옮기면 됩니다 (배선은 핀 이름 기준으로 따라오므로 끊어지지 않습니다).

핀 검증은 `wokwi-cli lint .` (아래 실행 방법 3 참고)로 브레드보드 핀 이름(`{열}{t|b}.{a-j}` 또는 `{t|b}{p|n}.{1-50}`) 오타를 잡을 수 있습니다.

## SHT31 / BH1750은 왜 시뮬레이션에 없는가

Wokwi 공식 부품에도, 재사용 가능한 커뮤니티 커스텀 칩에도 SHT31/BH1750이 없습니다 (`docs.wokwi.com`의 지원 하드웨어 목록에 미등재, GitHub에도 공개된 `chip.json`/`chip.c` 없음. 직접 만들려면 WASI-SDK로 C를 WASM으로 컴파일해야 해서 Phase 1 일정상 비효율적).

대신 `smartfarm_controller.ino`에 `WOKWI_SIMULATION` 빌드 플래그를 추가해서, 이 플래그가 정의된 경우에만 두 센서를 실제 I2C 호출 없이 "정상 응답 + 고정 패턴 값"으로 취급하도록 했습니다 (`setup()`, `publishSensorReading()`의 `#ifdef WOKWI_SIMULATION` 블록 참고). 실제 보드에 업로드할 때(Arduino IDE 등)는 이 플래그를 정의하지 않으므로 원래 로직(`sht31.begin(0x44)`, `lightMeter.begin(...)`) 그대로 동작합니다.

즉 이 시뮬레이션에서는 I2C 주소 충돌 여부 자체를 검증하지 않습니다 — `0x44`(SHT31)와 `0x23`(BH1750)는 겹치지 않는다는 것만 코드로 확인된 상태이고, 실제 버스 동작은 부품 도착 후 실기로 확인하세요.

## 실행 방법 1 — 브라우저 (설치 없이, 가장 빠름)

> 주의: 브라우저 에디터는 Wokwi가 직접 컴파일하며 `-DWOKWI_SIMULATION` 같은 커스텀 빌드 플래그를 지정할 수 없습니다. 그대로 실행하면 `sht31.begin(0x44)`/`lightMeter.begin(...)`가 시뮬레이션에 없는 실제 칩을 찾다가 실패해서 `air_temp`/`air_humidity`/`light_lux` 필드가 JSON에서 빠지는 정도로 동작합니다 (크래시는 아님). 두 값까지 채운 상태로 보고 싶다면 아래 "실행 방법 2"를 사용하세요.

1. https://wokwi.com 접속 → New Project → Arduino Uno 선택
2. `sketch.ino` 탭 내용을 이 저장소의 [smartfarm_controller.ino](../smartfarm_controller.ino) 내용으로 교체
3. 좌측 파일 목록에 `libraries.txt` 파일을 만들고 이 폴더의 [libraries.txt](libraries.txt) 내용을 붙여넣기 (Wokwi가 자동으로 라이브러리 설치)
4. `diagram.json` 탭 내용을 이 폴더의 [diagram.json](diagram.json) 내용으로 교체
5. ▶ Start Simulation, 시리얼 모니터에서 `sensor_reading` JSON이 5초마다 찍히는지 확인

## 트러블슈팅: `fatal error: Adafruit_SHT31.h: No such file or directory`

`libraries.txt`에 이름을 적어도 빌드가 실패하면 대부분 라이브러리가 실제로 설치되지 않은 경우입니다.

- **가장 확실한 방법**: 우측 상단 `Library Manager` 탭(`+` 버튼) → 라이브러리 이름 검색 → 클릭해서 추가. UI로 추가하면 의존 라이브러리도 함께 설치됩니다.
- `Adafruit SHT31 Library`는 내부적으로 `Adafruit BusIO`에 의존합니다. `libraries.txt`를 직접 수정하는 경우 반드시 `Adafruit BusIO`도 목록에 포함하세요 (이 저장소의 [libraries.txt](libraries.txt)에는 이미 포함되어 있습니다).
- 코드 에디터에서 `#include <Adafruit_SHT31.h>` 줄 아래 물결선(에러 표시)을 클릭하면 바로 설치 제안이 뜨는 경우도 있습니다.
- 수정 후에는 반드시 `SAVE` 한 번 누르고 다시 ▶ 실행하세요.

## 실행 방법 2 — VS Code + Wokwi 확장 (로컬 저장소와 동기화, 권장)

실제 저장소의 `.ino` 파일을 그대로 시뮬레이션에 사용하고 싶다면 이 방법을 쓰세요.

1. VS Code에 [Wokwi Simulator 확장](https://marketplace.visualstudio.com/items?itemName=Wokwi.wokwi-vscode) 설치 (Wokwi 계정 로그인 필요)
2. `arduino-cli` 설치 후 AVR 코어/라이브러리 준비:
   ```bash
   arduino-cli core install arduino:avr
   arduino-cli lib install ArduinoJson "Adafruit SHT31 Library" BH1750 OneWire DallasTemperature
   ```
3. `arduino/smartfarm_controller/` 에서 `WOKWI_SIMULATION` 플래그를 켠 채로 빌드 (SHT31/BH1750 값이 스텁으로 채워짐):
   ```bash
   cd "arduino/smartfarm_controller"
   arduino-cli compile --fqbn arduino:avr:uno --build-property "build.extra_flags=-DWOKWI_SIMULATION" --output-dir wokwi/build .
   ```
   `.ino`를 수정할 때마다 이 명령을 다시 실행해야 `wokwi.toml`이 읽는 `.hex`/`.elf`가 갱신됩니다 (자동 리빌드 아님). 실제 보드에 업로드할 때는 `--build-property` 없이(또는 Arduino IDE로) 컴파일해서 실제 센서 코드가 그대로 쓰이게 하세요.
4. VS Code에서 `wokwi/` 폴더를 열고 `diagram.json`을 연 뒤 F1 → `Wokwi: Start Simulator`

## 실행 방법 3 — `wokwi-cli`로 시리얼 명령 자동 테스트 (헤드리스)

안전 로직(펌프 거부 조건 등)처럼 시리얼로 JSON `command`를 보내고 응답을 확인해야 하는 테스트는 매번 VS Code 시리얼 모니터에 수동으로 타이핑하는 대신 [`scenario.yaml`](scenario.yaml)로 자동화할 수 있습니다.

1. CLI 설치 (최초 1회): `curl -L https://wokwi.com/ci/install.sh | sh`
2. https://wokwi.com/dashboard/ci 에서 토큰 발급 후 `WOKWI_CLI_TOKEN` 환경변수로 설정 (VS Code 확장 로그인과는 별개 토큰입니다). **토큰은 채팅/커밋 등에 절대 붙여넣지 말고 로컬 셸 환경변수나 안전한 `.env` 파일로만 관리하세요.**
3. (토큰 불필요, 배선 변경 시마다 먼저) `diagram.json` 핀 이름 정적 검사: `wokwi-cli lint .`
4. 이 폴더(`wokwi/`)에서 시나리오 실행:
   ```bash
   wokwi-cli --scenario scenario.yaml --timeout 15000 .
   ```
5. 3개 스텝 모두 `Expected text matched`가 뜨고 `Scenario completed successfully`로 끝나면 통과입니다.

> **알려진 이슈**: 시뮬레이션 시작 직후 첫 `write-serial` 전송은 맨 앞 1바이트가 깨져서 `deserializeJson` 실패(`invalid command json`)로 이어지는 현상이 있습니다. `scenario.yaml`은 이를 우회하기 위해 실제 명령 앞에 더미 `warmup` 줄을 한 번 보내서 흡수시킵니다. 새 시나리오를 추가할 때도 이 패턴을 유지하세요.

## Phase 1 체크리스트 연결

이 시뮬레이션으로 [노션 로드맵](https://app.notion.com/p/3908c13da92380cc9a5ffc9ac867199a) Phase 1 항목 중 아래를 검증하세요.

- [ ] I2C 주소 충돌 없음 (`0x44` vs `0x23`, 코드 리뷰로 확인 완료 — 실기 검증은 부품 도착 후)
- [x] 아날로그/디지털/PWM 핀 수 충분 (A0, D2, D3, D5, D6, D9) — `diagram.json` 배선 그대로 컴파일/부팅/센서 출력 정상 확인 (2026-07-02)
- [x] 수위 `low` 시 펌프 명령이 `safety_rules`에서 거부되는지 — `scenario.yaml`의 `wl-test`로 자동 검증, `rejected`/`water level low` 응답 확인 (2026-07-02)
- [x] `MAX_PUMP_RUN_MS` 초과 시 명령 자체가 거부되는지 — `scenario.yaml`의 `dur-test`(`duration_ms=15000` > 10000ms)로 자동 검증, `rejected`/`duration exceeds max pump run` 응답 확인 (2026-07-02)
- [ ] `DAILY_MAX_PUMP_MS`/`DAILY_MAX_WATERINGS` 초과 시 자동 정지/거부되는지 — 아직 미검증 (여러 번 연속 명령 필요, 후속 시나리오 추가 예정)
