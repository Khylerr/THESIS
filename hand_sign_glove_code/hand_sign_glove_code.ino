#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <BluetoothSerial.h>

// Hardware Pin Definitions
#define SDA_PIN 21
#define SCL_PIN 22          // Change to 27 if you remapped SCL during hardware repair
#define BOOT_BUTTON_PIN 0   // Built-in ESP32 BOOT button
const int FLEX_PINS[5] = {39, 34, 35, 32, 33};

// Timing Configurations (50 Hz / 20 ms frame period)
const unsigned long FRAME_PERIOD_MS = 20; 
unsigned long lastFrameTime = 0;

// Sensor Calibration Offsets
int flexOffsets[5] = {0, 0, 0, 0, 0};
float accelOffsets[3] = {0.0, 0.0, 0.0};
float gyroOffsets[3] = {0.0, 0.0, 0.0};
bool isCalibrated = false;

Adafruit_MPU6050 mpu;
BluetoothSerial SerialBT;

// I2C Bus Recovery Routine
void clearI2CBus() {
  pinMode(SDA_PIN, INPUT_PULLUP);
  pinMode(SCL_PIN, OUTPUT);

  for (int i = 0; i < 9; i++) {
    digitalWrite(SCL_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(SCL_PIN, LOW);
    delayMicroseconds(10);
  }
}

// Multi-Sample Calibration Function
void calibrateSensors() {
  Serial.println("\n------------------------------------------------");
  Serial.println(">>> CALIBRATING: Keep glove completely still! <<<");
  Serial.println("------------------------------------------------");

  long flexSum[5] = {0};
  float accelSum[3] = {0.0, 0.0, 0.0};
  float gyroSum[3] = {0.0, 0.0, 0.0};
  const int SAMPLES = 50;
  int validMpuSamples = 0;

  for (int i = 0; i < SAMPLES; i++) {
    // 1. Accumulate MPU6050 readings
    sensors_event_t accel, gyro, temp;
    if (mpu.getEvent(&accel, &gyro, &temp)) {
      accelSum[0] += accel.acceleration.x;
      accelSum[1] += accel.acceleration.y;
      accelSum[2] += accel.acceleration.z;

      gyroSum[0] += gyro.gyro.x;
      gyroSum[1] += gyro.gyro.y;
      gyroSum[2] += gyro.gyro.z;
      validMpuSamples++;
    }

    // 2. Accumulate Flex Sensor readings
    for (int f = 0; f < 5; f++) {
      flexSum[f] += analogRead(FLEX_PINS[f]);
    }

    delay(10); // Small sampling delay across calibration window
  }

  // Calculate averages for offsets
  if (validMpuSamples > 0) {
    accelOffsets[0] = accelSum[0] / validMpuSamples;
    accelOffsets[1] = accelSum[1] / validMpuSamples;
    accelOffsets[2] = accelSum[2] / validMpuSamples;

    gyroOffsets[0] = gyroSum[0] / validMpuSamples;
    gyroOffsets[1] = gyroSum[1] / validMpuSamples;
    gyroOffsets[2] = gyroSum[2] / validMpuSamples;
  }

  for (int f = 0; f < 5; f++) {
    flexOffsets[f] = flexSum[f] / SAMPLES;
  }

  isCalibrated = true;
  Serial.println(">>> CALIBRATION SUCCESSFUL: All readings zeroed! <<<\n");
}

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000);

  // Configure BOOT button
  pinMode(BOOT_BUTTON_PIN, INPUT_PULLUP);

  SerialBT.begin("ESP32_Glove_Controller"); 
  Serial.println("\n--- ESP32 Glove Controller (50Hz + Calibration) ---");

  // Bus recovery and I2C setup
  clearI2CBus();
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setTimeOut(1000);
  Wire.setClock(400000); // 400 kHz Fast Mode

  if (!mpu.begin()) {
    Serial.println("ERROR: MPU6050 not detected!");
    while (1) { delay(10); }
  }

  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_44_HZ);

  for (int i = 0; i < 5; i++) {
    pinMode(FLEX_PINS[i], INPUT);
  }

  Serial.println("System Ready! Press the BOOT button on ESP32 anytime to set zero points.");
  
  // Auto-calibrate once on startup
  calibrateSensors();
  lastFrameTime = millis();
}

void loop() {
  // Check if BOOT button is pressed (Active LOW)
  if (digitalRead(BOOT_BUTTON_PIN) == LOW) {
    calibrateSensors();
    // Wait until button is released to prevent repeated triggers
    while (digitalRead(BOOT_BUTTON_PIN) == LOW) { delay(10); }
  }

  unsigned long currentMillis = millis();

  // 50 Hz Frame Sampling
  if (currentMillis - lastFrameTime >= FRAME_PERIOD_MS) {
    lastFrameTime = currentMillis;

    // A. Read MPU6050 Data
    sensors_event_t accel, gyro, temp;
    if (!mpu.getEvent(&accel, &gyro, &temp)) {
      Serial.println("WARNING: MPU6050 read failed");
      return;
    }

    // B. Calculate Zero-Offset MPU Data
    float calAccelX = accel.acceleration.x - accelOffsets[0];
    float calAccelY = accel.acceleration.y - accelOffsets[1];
    float calAccelZ = accel.acceleration.z - accelOffsets[2];

    float calGyroX = gyro.gyro.x - gyroOffsets[0];
    float calGyroY = gyro.gyro.y - gyroOffsets[1];
    float calGyroZ = gyro.gyro.z - gyroOffsets[2];

    // C. Read & Calculate Zero-Offset Flex Sensor Data
    int calFlex[5];
    for (int i = 0; i < 5; i++) {
      calFlex[i] = analogRead(FLEX_PINS[i]) - flexOffsets[i];
    }

    // D. Format Payload String
    char buffer[160];
    snprintf(buffer, sizeof(buffer),
      "[FLEX] F1:%d F2:%d F3:%d F4:%d F5:%d | [ACCEL] X:%.2f Y:%.2f Z:%.2f | [GYRO] X:%.2f Y:%.2f Z:%.2f",
      calFlex[0], calFlex[1], calFlex[2], calFlex[3], calFlex[4],
      calAccelX, calAccelY, calAccelZ,
      calGyroX, calGyroY, calGyroZ
    );

    // E. Transmit Payload
    Serial.println(buffer);

    if (SerialBT.hasClient()) {
      SerialBT.println(buffer);
    }
  }
}