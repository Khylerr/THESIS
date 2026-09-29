#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>

#define SDA_PIN 21
#define SCL_PIN 22
const int FLEX_PINS[5] = {39, 34, 35, 32, 33};

// Test Setup
const int SAMPLES = 500;             // 500 samples at 50 Hz = 10 Seconds
const float TS = 0.02;               // 20 ms frame period
const float ALPHA = 0.25;            // EMA filter factor (fc ≈ 2.29 Hz)

// Full Scale Ranges for Normalized % Variance Calculations
const float FSR_FLEX = 4095.0;
const float FSR_ACCEL = 156.96;      // ±8g range (8 * 9.81 * 2)
const float FSR_GYRO = 17.453;       // ±500 deg/s range (500 * (PI/180) * 2)

float flexRaw[5][SAMPLES];
float flexFiltered[5][SAMPLES];
float accelX[SAMPLES], gyroX[SAMPLES];

Adafruit_MPU6050 mpu;

float calcVariance(float data[], float mean, int n) {
  float sum = 0;
  for (int i = 0; i < n; i++) {
    sum += (data[i] - mean) * (data[i] - mean);
  }
  return sum / (n - 1);
}

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000);

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setTimeOut(1000);
  Wire.setClock(400000);

  if (!mpu.begin()) {
    Serial.println("ERROR: MPU6050 initialization failed!");
    while (1);
  }

  // 1. Enforce MPU6050 Cutoff < 25Hz (Setting to 21 Hz)
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

  for (int i = 0; i < 5; i++) pinMode(FLEX_PINS[i], INPUT);

  Serial.println("\n========================================================");
  Serial.println("   REQUIREMENT COMPLIANCE AUDIT (50Hz / 10s Static Test)");
  Serial.println("========================================================");
  Serial.println("Hold board still... Sampling started.");

  float lastFilt[5] = {0};

  for (int s = 0; s < SAMPLES; s++) {
    unsigned long start = micros();

    sensors_event_t a, g, temp;
    mpu.getEvent(&a, &g, &temp);
    accelX[s] = a.acceleration.x;
    gyroX[s]  = g.gyro.x;

    for (int f = 0; f < 5; f++) {
      float raw = (float)analogRead(FLEX_PINS[f]);
      flexRaw[f][s] = raw;
      if (s == 0) lastFilt[f] = raw;
      else lastFilt[f] = ALPHA * raw + (1.0 - ALPHA) * lastFilt[f];
      flexFiltered[f][s] = lastFilt[f];
    }

    while (micros() - start < 20000); // 50 Hz Timing
  }

  // -----------------------------------------------------------
  // REQUIREMENT 1 AUDIT: LOW-PASS FILTER CUTOFF (< 25 Hz)
  // -----------------------------------------------------------
  float flex_fc = -log(1.0 - ALPHA) / (2.0 * PI * TS);
  float mpu_fc = 21.0; // MPU6050_BAND_21_HZ

  Serial.println("\n--- 1. FILTER CUTOFF FREQUENCY AUDIT ---");
  Serial.printf("Requirement: Cutoff Frequency < 25.0 Hz\n");
  Serial.printf("Flex LPF Cutoff (EMA α=%.2f) : %5.2f Hz -> [%s]\n", ALPHA, flex_fc, flex_fc < 25.0 ? "PASS" : "FAIL");
  Serial.printf("MPU6050 Hardware LPF Cutoff  : %5.2f Hz -> [%s]\n", mpu_fc, mpu_fc < 25.0 ? "PASS" : "FAIL");

  // -----------------------------------------------------------
  // REQUIREMENT 2 AUDIT: STATIC SIGNAL VARIANCE (< 2.0%)
  // -----------------------------------------------------------
  Serial.println("\n--- 2. STATIC SIGNAL VARIANCE AUDIT ---");
  Serial.println("Requirement: Normalized Variance < 2.000%");

  // Flex Sensors Audit
  for (int f = 0; f < 5; f++) {
    float sumFilt = 0;
    for (int s = 0; s < SAMPLES; s++) sumFilt += flexFiltered[f][s];
    float mean = sumFilt / SAMPLES;
    float var = calcVariance(flexFiltered[f], mean, SAMPLES);
    
    // Normalized Variance % relative to 4095 ADC Full Scale
    float pctVarFSR = (var / (FSR_FLEX * FSR_FLEX)) * 100.0;
    // Relative Noise % relative to Mean
    float pctStdMean = (sqrt(var) / (mean > 0 ? mean : 1.0)) * 100.0;

    Serial.printf("Flex %d (ADC %d): Var(σ²)=%.4f | %%Var(FSR)=%.6f%% | CoeffVar=%.3f%% -> [%s]\n",
                  f + 1, FLEX_PINS[f], var, pctVarFSR, pctStdMean, (pctVarFSR < 2.0 && pctStdMean < 2.0) ? "PASS" : "FAIL");
  }

  // MPU6050 Accel Audit
  float sumA = 0;
  for (int s = 0; s < SAMPLES; s++) sumA += accelX[s];
  float meanA = sumA / SAMPLES;
  float varA = calcVariance(accelX, meanA, SAMPLES);
  float pctVarA = (varA / (FSR_ACCEL * FSR_ACCEL)) * 100.0;
  Serial.printf("MPU Accel X    : Var(σ²)=%.6f | %%Var(FSR)=%.6f%% -> [%s]\n",
                varA, pctVarA, pctVarA < 2.0 ? "PASS" : "FAIL");

  // MPU6050 Gyro Audit
  float sumG = 0;
  for (int s = 0; s < SAMPLES; s++) sumG += gyroX[s];
  float meanG = sumG / SAMPLES;
  float varG = calcVariance(gyroX, meanG, SAMPLES);
  float pctVarG = (varG / (FSR_GYRO * FSR_GYRO)) * 100.0;
  Serial.printf("MPU Gyro X     : Var(σ²)=%.6f | %%Var(FSR)=%.6f%% -> [%s]\n",
                varG, pctVarG, pctVarG < 2.0 ? "PASS" : "FAIL");

  Serial.println("========================================================\n");
}

void loop() {}