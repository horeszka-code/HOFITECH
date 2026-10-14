# SmartMic TF220 Android APK
Native Android WebView wrapper for the existing SmartMic acoustic analyzer deployed at https://smartmic-tf220-flow.onrender.com.

## Install
Download the workflow artifact **SmartMic-TF220-Android-APK**, unzip it, and install app-debug.apk on Android. This is a **debug-signed pilot build**, not a Play Store release.

## Build
GitHub Actions: Actions > Build SmartMic Android APK > latest successful run > artifact.
The APK requires internet; video analysis remains on the Render server. Videos are selected from the Android file picker. Nothing runs locally for acoustic calculation.
