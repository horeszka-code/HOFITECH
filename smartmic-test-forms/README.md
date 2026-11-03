# SmartMic Test Forms – Android PWA

This is a standalone web app deployed to Render Static Site. It reads DOCX files locally using browser APIs and generates editable research forms from color-coded Word table cells.

- Yellow cells: single-choice answer buttons
- Green cells: up to 8 photos per question
- Blue cells: up to 8 videos per question
- Plain text cells: measurements and notes
- SAVE: DOCX with inline photos; ZIP including DOCX and videos when videos exist

## Privacy

The source application is public, but **NO research test documents, collected photos, videos or completed DOCX files are included in this repository or on Render.** Uploaded test materials remain in browser memory and IndexedDB on the operator's device. Render serves only static app assets. The SAVE export downloads to the current device and is not a central archive.

## Install on Android

Open the HTTPS Render URL in Android Chrome, select **Install app** / **Add to Home screen**. The first load caches app assets for offline use. Native camera/video app launch through HTML file input capture hints may vary by Android device and browser.

## Limitations

Prototype 0.1.1 – no authentication, multi-operator sync, cryptographic signatures or central backups. Photos are JPEG-compressed for Word; videos remain separate files in a ZIP. Large videos can exceed available browser memory. The importer expects the HOFITECH Word template conventions, not arbitrary Word documents.

Do not commit source DOCX test assignments or completed research records to the public repository.
