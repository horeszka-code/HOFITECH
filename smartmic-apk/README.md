# SmartMic Test Forms – offline Android APK (v0.3.0)

**This project is separate from the Render PWA. Do not modify `smartmic-test-forms/` on the PWA deployment branch.**

## Functionality

- Imports an HOFITECH test assignment from a locally selected DOCX file and interprets the Word table-cell colors.
- Yellow table cells: selectable answers with a checkmark in the resulting Word document.
- Green photo cells: up to 8 photos from camera OR gallery per question, inserted into original DOCX and the PDF summary.
- Blue video cells: up to 8 videos per question, stored in the ZIP archive (the DOCX includes relative links to those files).
- Offline local autosave in IndexedDB (including captured media, if there is sufficient free storage).
- On **SAVE**, creates an original-format populated DOCX and a searchable native Android PDF with all fields and photos. If videos are present, saves an additional ZIP (DOCX + videos).
- PDF rendering uses `android.graphics.pdf.PdfDocument` and the system font, including Slovak accents. **PDF is a structured report, not a pixel-identical rendering of the Word template.**
- On Android 10 and newer, exports to the public **Downloads/SmartMic** directory through Android's MediaStore; on older Android, falls back to app-specific documents storage.
- No internet, hosted APIs, or remote DOCX conversion services are required after APK installation.

## Build from source

The GitHub Actions workflow `.github/workflows/build-smartmic-apk.yml` builds a debug-signed APK automatically when `smartmic-apk/` changes on the `smartmic-apk` branch.

Alternatively with Android SDK and JDK 21 on a local machine:

```bash
npm install
npm run build
npx cap add android
cp native/com/hofitech/smartmicforms/*.java android/app/src/main/java/com/hofitech/smartmicforms/
cd android && ./gradlew assembleDebug
```

Android output: `android/app/build/outputs/apk/debug/app-debug.apk`.

APK debug builds are for internal testing and cannot be updated over a production-signed version without reinstalling. For real deployment, set up a controlled signing keystore and release pipeline.

## Architecture

- `www/index.html`: offline Word import/edit DOCX serializer, unchanged tested business logic with APK-specific SAVE wrapper.
- `www/native-bridge.js`: Capacitor JS-to-native registration.
- `www/photo-upgrades.js`: camera/gallery chooser, full-screen in-app viewer with Back, and native photo copy to Pictures/SmartMic.
- `native/com/hofitech/smartmicforms/SmartMicNativePlugin.java`: native PDF generator and chunked exports to public Downloads.
- `native/com/hofitech/smartmicforms/MainActivity.java`: plugin registration.
- `capacitor.config.json`: distinct application id with *no* `server.url` (assets are packaged into APK).
- `tests/smoke-test.py`: browser-level integration test for DOCX and mocked native export, including a sample image.

## Data privacy and operational cautions

Only the **application source** is committed to GitHub. Test assignments, photo/video evidence, operator records and completed files must stay off the public repository. PDF export is native and local.

Offline local storage is *not a backup*. Export records after each test and copy the results to an approved backup location. The prototype currently holds one active draft; multi-test history, staff login and audit logging are future enhancements.

Camera and video capture depend on the device's installed camera application and may require runtime permission checks on specific tablets. For large video experiments, monitor free disk space and memory; large ZIP creation remains in browser memory.
## v0.3 gallery workflow and safe parallel test

- Tap any empty green photo slot: choose **Odfotiť fotoaparátom** or **Vybrať z galérie**.
- When a photo enters a test, the form/draft is saved first; a copy is then written to public **Pictures/SmartMic** and visible in the Android Gallery. Importing from Gallery creates an additional SmartMic album copy.
- Tap an existing photo or video to open the in-app viewer, and use **← Späť k formuláru** to return without losing draft data.
- For safety, v0.3 uses Android app ID `com.hofitech.smartmicforms.v03`, separate from v0.2. Both can be installed side-by-side; drafts are NOT automatically transferred. Avoid uninstalling v0.2 until the old test has been exported.
- Photo album export needs Android 10+ MediaStore; on Android 9 and earlier the runtime legacy storage permission is requested. When gallery storage fails, the photo remains in the draft and a warning is displayed.
- V0.3 debug APK signing is development-only; future stable signed release should use a controlled private keystore.
