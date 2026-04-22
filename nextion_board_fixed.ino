#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "Nextion.h"

// ================= WIFI =================
const char* ssid = "Dheeraj";
const char* password = "dheerubs";

// Use your Flask server LAN IP here (avoid attendance.local on ESP32).
const char* SERVER_IP = "192.168.1.14";
const uint16_t SERVER_PORT = 5000;
String SERVER = String("http://") + SERVER_IP + ":" + String(SERVER_PORT);

// ================= NEXTION UART =================
#define NEXTION_RX 16
#define NEXTION_TX 17

// Keep this at 9600 unless your Nextion baud is explicitly set to 115200.
#define NEXTION_BAUD 9600

// ================= NEXTION OBJECTS =================
NexPage page0 = NexPage(0, 0, "page0");
NexPage page1 = NexPage(1, 0, "page1");
NexPicture pStatus = NexPicture(1, 1, "pStatus");
NexText tName = NexText(1, 2, "tName");
NexProgressBar jProg = NexProgressBar(1, 3, "jProg");
NexText tEnrollStatus = NexText(1, 4, "tEnrollStatus");

NexPage page2 = NexPage(2, 0, "page2");
NexPicture pFace = NexPicture(2, 1, "pFace");
NexText tPerson = NexText(2, 2, "tPerson");
NexText tStatus = NexText(2, 3, "tStatus");
NexText tConf = NexText(2, 4, "tConf");

bool enrollMode = false;
bool attendMode = false;
String currentName = "";
unsigned long modeLockUntil = 0;

int lastEnrollCount = -1;
String lastEnrollText = "";
String lastAttendName = "";
String lastAttendEntry = "";
int lastAttendConfidence = -1;
String lastAttendStatus = "";
unsigned long lastBoardPingMs = 0;

String readNextionCommand() {
  String cmd = "";
  unsigned long start = millis();

  while (millis() - start < 300) {
    while (Serial2.available()) {
      uint8_t c = Serial2.read();
      if (c == 0xFF) {
        while (Serial2.available() && Serial2.peek() == 0xFF) Serial2.read();
        cmd.trim();
        return cmd;
      }
      cmd += (char)c;
    }
  }
  cmd.trim();
  return cmd;
}

void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.println("[WiFi] Reconnecting...");
  WiFi.disconnect(true);
  delay(200);
  WiFi.begin(ssid, password);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 12000) {
    delay(400);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[WiFi] Connected, IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("[WiFi] Failed to reconnect");
  }
}

String httpGET(String endpoint) {
  if (WiFi.status() != WL_CONNECTED) return "";

  WiFiClient client;
  HTTPClient http;
  String url = SERVER + endpoint;
  http.setTimeout(3000);
  http.begin(client, url);
  int code = http.GET();
  String res = (code == 200) ? http.getString() : "";
  Serial.println("GET " + endpoint + " => " + String(code));
  http.end();
  return res;
}

int httpPOST(String endpoint, String payload) {
  if (WiFi.status() != WL_CONNECTED) return -1;

  WiFiClient client;
  HTTPClient http;
  String url = SERVER + endpoint;
  http.setTimeout(3000);
  http.begin(client, url);
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(payload);
  String res = http.getString();
  http.end();

  Serial.println("POST " + endpoint + " => " + String(code));
  Serial.println(res);
  return code;
}

bool checkServerOnline() {
  String res = httpGET("/status");
  if (res.length() == 0) {
    Serial.println("[Server] Not reachable. Check SERVER_IP and firewall.");
    return false;
  }
  Serial.println("[Server] Reachable");
  return true;
}

void sendBoardPing() {
  if (millis() - lastBoardPingMs < 5000) return;
  lastBoardPingMs = millis();
  int code = httpPOST("/board_ping", "{}");
  if (code != 200) {
    Serial.println("[Board] Ping failed");
  }
}

void setMode(String mode, String name = "") {
  String body = "{\"type\":\"" + mode + "\",\"name\":\"" + name + "\"}";
  int code = httpPOST("/mode", body);

  if (code != 200) {
    Serial.println("[Mode] Change failed");
  } else {
    Serial.println("[Mode] Changed: " + mode);
  }
}

void safeDelay() { delay(10); }

void showHome() {
  page0.show();
  delay(200);
}

void resetAttendUI() {
  pFace.setPic(0); safeDelay();
  tPerson.setText("--"); safeDelay();
  tStatus.setText("WAIT"); safeDelay();
  tConf.setText(""); safeDelay();

  lastAttendName = "";
  lastAttendEntry = "";
  lastAttendConfidence = -1;
  lastAttendStatus = "";
}

void resetEnrollUI() {
  jProg.setValue(0); safeDelay();
  pStatus.setPic(0); safeDelay();
  tEnrollStatus.setText(""); safeDelay();

  lastEnrollCount = -1;
  lastEnrollText = "";
}

void checkNextionSerial() {
  if (!Serial2.available()) return;
  String cmd = readNextionCommand();
  if (cmd.length() == 0) return;

  Serial.println("CMD RECEIVED: [" + cmd + "]");

  if (cmd == "ENROLL") {
    page1.show(); safeDelay();
    tName.setText("Enter Name"); safeDelay();
    tEnrollStatus.setText(""); safeDelay();
    resetEnrollUI();
    enrollMode = false;
    attendMode = false;
  }
  else if (cmd == "START") {
    char buf[40];
    tName.getText(buf, sizeof(buf));
    currentName = String(buf);
    currentName.trim();

    if (currentName.length() < 2 || currentName == "Enter Name") {
      tEnrollStatus.setText("Invalid Name"); safeDelay();
      return;
    }

    modeLockUntil = millis() + 2500;
    setMode("enroll", currentName);
    enrollMode = true;
    attendMode = false;

    jProg.setValue(0); safeDelay();
    pStatus.setPic(1); safeDelay();
    tEnrollStatus.setText("Look at Camera"); safeDelay();
  }
  else if (cmd == "ATTEND") {
    page2.show(); safeDelay();
    modeLockUntil = millis() + 1500;
    setMode("attend");
    attendMode = true;
    enrollMode = false;
    resetAttendUI();
  }
  else if (cmd == "BACK") {
    setMode("idle");
    enrollMode = false;
    attendMode = false;
    showHome();
  }
}

void setup() {
  Serial.begin(115200);
  Serial2.begin(NEXTION_BAUD, SERIAL_8N1, NEXTION_RX, NEXTION_TX);
  Serial2.setRxBufferSize(1024);
  Serial2.setTxBufferSize(1024);
  nexInit();

  WiFi.begin(ssid, password);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\n[WiFi] Connected");
  Serial.print("[WiFi] ESP32 IP: ");
  Serial.println(WiFi.localIP());
  Serial.print("[Server] Base URL: ");
  Serial.println(SERVER);

  checkServerOnline();
  showHome();
}

void loop() {
  ensureWifi();
  sendBoardPing();
  checkNextionSerial();

  if (enrollMode) {
    String res = httpGET("/status");
    if (res.length() == 0) return;

    DynamicJsonDocument doc(1024);
    if (deserializeJson(doc, res) != DeserializationError::Ok) return;

    int count = doc["enroll_count"] | 0;
    if (count != lastEnrollCount) {
      lastEnrollCount = count;
      jProg.setValue(count * 10); safeDelay();
      String text = "Captured " + String(count) + "/10";
      if (text != lastEnrollText) {
        lastEnrollText = text;
        tEnrollStatus.setText(text.c_str()); safeDelay();
      }
      pStatus.setPic(2); safeDelay();
    }

    if (count >= 10) {
      pStatus.setPic(3); safeDelay();
      tEnrollStatus.setText("Enroll Complete"); safeDelay();
      enrollMode = false;
      lastEnrollCount = -1;
      lastEnrollText = "";
      delay(1500);
      showHome();
    }
  }

  if (attendMode) {
    String res = httpGET("/last_recognition");
    if (res.length() == 0) return;

    DynamicJsonDocument doc(1024);
    if (deserializeJson(doc, res) != DeserializationError::Ok) return;

    String status = doc["status"] | "";
    if (status != lastAttendStatus) {
      lastAttendStatus = status;
    }

    if (status == "ATTENDANCE_MARKED") {
      String name = doc["name"].as<String>();
      String entry = doc["entry"].as<String>();
      int confidence = doc["confidence"] | 0;

      if (name != lastAttendName) {
        lastAttendName = name;
        tPerson.setText(name.c_str()); safeDelay();
      }
      if (entry != lastAttendEntry) {
        lastAttendEntry = entry;
        tStatus.setText(entry.c_str()); safeDelay();
      }
      if (confidence != lastAttendConfidence) {
        lastAttendConfidence = confidence;
        tConf.setText((String(confidence) + "%").c_str()); safeDelay();
      }

      pFace.setPic(6); safeDelay();
      delay(1200);
    }
    else if (status == "UNKNOWN") {
      tPerson.setText("--"); safeDelay();
      tStatus.setText("UNKNOWN"); safeDelay();
      tConf.setText(""); safeDelay();
      pFace.setPic(7); safeDelay();
    }
    else if (status == "NO_FACE") {
      tPerson.setText("--"); safeDelay();
      tStatus.setText("NO FACE"); safeDelay();
      tConf.setText(""); safeDelay();
      pFace.setPic(8); safeDelay();
    }
  }

  delay(50);
}
