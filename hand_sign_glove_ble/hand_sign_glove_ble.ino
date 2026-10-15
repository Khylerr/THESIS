/*
 * AISL-A glove firmware - BLE version
 * ESP32-DevKitC (WROOM-32) + 5 flex sensors + MPU6050 (optional)
 *
 * Transport: Bluetooth Low Energy (GATT notifications), 50 Hz.
 * Device name: "AISL_Glove"
 *
 * BLE service  e1273d67-cf0f-4bb7-9477-4f5d92124a6f
 *   DATA   ecbd02f0-...  notify  29-byte binary packet per sample (layout below)
 *   STATUS 493ccb74-...  notify  text: MPU:OK / MPU:MISSING / CAL:START / CAL:DONE ... / PONG:<n>
 *   CMD    b8b472e5-...  write   text: "CAL" = recalibrate, "PING:<n>" = latency probe
 *
 * DATA packet (little-endian, 29 bytes):
 *   uint16  seq           packet counter (detects dropped packets)
 *   uint32  t_ms          ESP32 millis() when the sample was read (device clock)
 *   int16   flex[5]       calibrated ADC counts (raw - baseline), F1..F5
 *   int16   acc[3]        m/s^2 * 100
 *   int16   gyro[3]       rad/s * 1000
 *   uint8   flags         bit0 MPU ok, bit1 calibrated, bit2..6 flex F1..F5 saturated (raw <=5 or >=4090)
 *
 * USB Serial (115200) still prints a human-readable line per sample for debugging.
 * Press the BOOT button (or send "CAL") to re-check the MPU and recalibrate.
 */
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// ---------------- Hardware ----------------
#define SDA_PIN 21
#define SCL_PIN 22          // Change to 27 if you remapped SCL during hardware repair
#define BOOT_BUTTON_PIN 0   // Built-in ESP32 BOOT button
const int FLEX_PINS[5] = {39, 34, 35, 32, 33};

// ---------------- Timing ----------------
const unsigned long FRAME_PERIOD_MS = 20;   // 50 Hz. (1000 = 1 per second for reading by eye)
const bool PRINT_USB_LINES = true;          // human-readable line on USB Serial each sample

// ---------------- BLE ----------------
#define DEVICE_NAME   "AISL_Glove"
#define SERVICE_UUID  "e1273d67-cf0f-4bb7-9477-4f5d92124a6f"
#define DATA_UUID     "ecbd02f0-3d5f-4ad5-952a-9e75b163eeab"
#define STATUS_UUID   "493ccb74-46cd-4966-8a16-ba3cca3fd116"
#define CMD_UUID      "b8b472e5-964d-4b06-ae50-19a91cccb0a2"

struct __attribute__((packed)) GlovePacket {
  uint16_t seq;
  uint32_t t_ms;
  int16_t flex[5];
  int16_t acc[3];
  int16_t gyro[3];
  uint8_t flags;
};
static_assert(sizeof(GlovePacket) == 29, "packet must be 29 bytes");

BLEServer* bleServer = nullptr;
BLECharacteristic* dataChar = nullptr;
BLECharacteristic* statusChar = nullptr;
volatile bool bleConnected = false;
bool wasConnected = false;

// Commands arrive in a BLE callback; handle them in loop()
volatile bool cmdCalibrate = false;
volatile bool cmdPing = false;
String pingId = "";

// ---------------- Sensors / calibration ----------------
Adafruit_MPU6050 mpu;
bool mpuOK = false;
bool isCalibrated = false;
int flexOffsets[5] = {0, 0, 0, 0, 0};
float accelOffsets[3] = {0, 0, 0};
float gyroOffsets[3] = {0, 0, 0};
uint16_t seq = 0;
unsigned long lastFrameTime = 0;

// ---------------- Helpers ----------------
void sendStatus(const String& msg) {
  Serial.println(msg);
  if (bleConnected && statusChar) {
    statusChar->setValue(msg);
    statusChar->notify();
  }
}

int16_t clamp16(float v) {
  if (v > 32767) return 32767;
  if (v < -32768) return -32768;
  return (int16_t)lroundf(v);
}

class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer* s) override { bleConnected = true; }
  void onDisconnect(BLEServer* s) override { bleConnected = false; }
};

class CmdCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* c) override {
    String v = c->getValue();
    v.trim();
    if (v == "CAL") {
      cmdCalibrate = true;
    } else if (v.startsWith("PING:")) {
      pingId = v.substring(5);
      cmdPing = true;
    }
  }
};

void clearI2CBus() {
  pinMode(SDA_PIN, INPUT_PULLUP);
  pinMode(SCL_PIN, OUTPUT);
  for (int i = 0; i < 9; i++) {
    digitalWrite(SCL_PIN, HIGH); delayMicroseconds(10);
    digitalWrite(SCL_PIN, LOW);  delayMicroseconds(10);
  }
}

bool initMPU() {
  clearI2CBus();
  Wire.end();
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setTimeOut(1000);
  Wire.setClock(400000);
  if (!mpu.begin()) {
    sendStatus("MPU:MISSING (sending zeros for accel/gyro)");
    return false;
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_44_HZ);
  sendStatus("MPU:OK");
  return true;
}

void calibrateSensors() {
  sendStatus("CAL:START keep glove still");
  long flexSum[5] = {0};
  float aSum[3] = {0, 0, 0}, gSum[3] = {0, 0, 0};
  const int SAMPLES = 50;
  int validMpu = 0;

  for (int i = 0; i < SAMPLES; i++) {
    if (mpuOK) {
      sensors_event_t a, g, t;
      if (mpu.getEvent(&a, &g, &t)) {
        aSum[0] += a.acceleration.x; aSum[1] += a.acceleration.y; aSum[2] += a.acceleration.z;
        gSum[0] += g.gyro.x;         gSum[1] += g.gyro.y;         gSum[2] += g.gyro.z;
        validMpu++;
      }
    }
    for (int f = 0; f < 5; f++) flexSum[f] += analogRead(FLEX_PINS[f]);
    delay(10);
  }
  if (validMpu > 0) {
    for (int k = 0; k < 3; k++) {
      accelOffsets[k] = aSum[k] / validMpu;
      gyroOffsets[k] = gSum[k] / validMpu;
    }
  }
  for (int f = 0; f < 5; f++) flexOffsets[f] = flexSum[f] / SAMPLES;
  isCalibrated = true;

  // Calibration baselines (raw ADC counts + IMU offsets) - logged by the recorder
  char buf[200];
  snprintf(buf, sizeof(buf),
           "CAL:DONE flex=%d,%d,%d,%d,%d acc=%.3f,%.3f,%.3f gyro=%.4f,%.4f,%.4f mpu=%d",
           flexOffsets[0], flexOffsets[1], flexOffsets[2], flexOffsets[3], flexOffsets[4],
           accelOffsets[0], accelOffsets[1], accelOffsets[2],
           gyroOffsets[0], gyroOffsets[1], gyroOffsets[2], mpuOK ? 1 : 0);
  sendStatus(String(buf));
}

void setupBLE() {
  BLEDevice::init(DEVICE_NAME);
  BLEDevice::setMTU(100);  // packet is 29 bytes; default BLE payload is only 20
  bleServer = BLEDevice::createServer();
  bleServer->setCallbacks(new ServerCallbacks());

  BLEService* service = bleServer->createService(SERVICE_UUID);

  dataChar = service->createCharacteristic(DATA_UUID, BLECharacteristic::PROPERTY_NOTIFY);
  dataChar->addDescriptor(new BLE2902());

  statusChar = service->createCharacteristic(
      STATUS_UUID, BLECharacteristic::PROPERTY_NOTIFY | BLECharacteristic::PROPERTY_READ);
  statusChar->addDescriptor(new BLE2902());

  BLECharacteristic* cmdChar = service->createCharacteristic(
      CMD_UUID, BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  cmdChar->setCallbacks(new CmdCallbacks());

  service->start();
  BLEAdvertising* adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(SERVICE_UUID);
  adv->setScanResponse(true);
  BLEDevice::startAdvertising();
  Serial.println("BLE advertising as \"" DEVICE_NAME "\"");
}

// ---------------- Setup / loop ----------------
void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000);
  pinMode(BOOT_BUTTON_PIN, INPUT_PULLUP);
  for (int i = 0; i < 5; i++) pinMode(FLEX_PINS[i], INPUT);

  Serial.println("\n--- AISL-A Glove (BLE, 50 Hz) ---");
  setupBLE();
  mpuOK = initMPU();
  calibrateSensors();
  lastFrameTime = millis();
}

void loop() {
  // Connection changes: re-advertise after a disconnect, re-send status after a connect
  if (!bleConnected && wasConnected) {
    delay(200);
    bleServer->startAdvertising();
    Serial.println("BLE disconnected, advertising again");
  }
  if (bleConnected && !wasConnected) {
    Serial.println("BLE connected");
    delay(300);  // give the client time to subscribe
    sendStatus(mpuOK ? "MPU:OK" : "MPU:MISSING (sending zeros for accel/gyro)");
  }
  wasConnected = bleConnected;

  // Commands
  if (cmdPing) {           // answer immediately: used for round-trip latency
    cmdPing = false;
    sendStatus("PONG:" + pingId);
  }
  bool bootPressed = digitalRead(BOOT_BUTTON_PIN) == LOW;
  if (cmdCalibrate || bootPressed) {
    cmdCalibrate = false;
    if (!mpuOK) mpuOK = initMPU();
    calibrateSensors();
    while (digitalRead(BOOT_BUTTON_PIN) == LOW) delay(10);
    lastFrameTime = millis();
  }

  unsigned long now = millis();
  if (now - lastFrameTime < FRAME_PERIOD_MS) return;
  lastFrameTime += FRAME_PERIOD_MS;
  if (now - lastFrameTime > 5 * FRAME_PERIOD_MS) lastFrameTime = now;  // don't burst after a stall

  GlovePacket p;
  p.seq = seq++;
  p.t_ms = millis();
  p.flags = (mpuOK ? 0x01 : 0) | (isCalibrated ? 0x02 : 0);

  for (int i = 0; i < 5; i++) {
    int raw = analogRead(FLEX_PINS[i]);
    if (raw <= 5 || raw >= 4090) p.flags |= (1 << (2 + i));
    p.flex[i] = raw - flexOffsets[i];
  }

  float ax = 0, ay = 0, az = 0, gx = 0, gy = 0, gz = 0;
  if (mpuOK) {
    sensors_event_t a, g, t;
    if (mpu.getEvent(&a, &g, &t)) {
      ax = a.acceleration.x - accelOffsets[0];
      ay = a.acceleration.y - accelOffsets[1];
      az = a.acceleration.z - accelOffsets[2];
      gx = g.gyro.x - gyroOffsets[0];
      gy = g.gyro.y - gyroOffsets[1];
      gz = g.gyro.z - gyroOffsets[2];
    }
  }
  p.acc[0] = clamp16(ax * 100);  p.acc[1] = clamp16(ay * 100);  p.acc[2] = clamp16(az * 100);
  p.gyro[0] = clamp16(gx * 1000); p.gyro[1] = clamp16(gy * 1000); p.gyro[2] = clamp16(gz * 1000);

  if (bleConnected) {
    dataChar->setValue((uint8_t*)&p, sizeof(p));
    dataChar->notify();
  }

  if (PRINT_USB_LINES) {
    char line[180];
    snprintf(line, sizeof(line),
             "[FLEX] F1:%d F2:%d F3:%d F4:%d F5:%d | [ACCEL] X:%.2f Y:%.2f Z:%.2f | [GYRO] X:%.2f Y:%.2f Z:%.2f",
             p.flex[0], p.flex[1], p.flex[2], p.flex[3], p.flex[4], ax, ay, az, gx, gy, gz);
    Serial.println(line);
  }
}
