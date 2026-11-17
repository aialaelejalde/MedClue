# MedClue requirements

## 1. Product overview

MedClue is an Android app that helps users identify medicines from package photos and manage a personal medicine cabinet.

## 2. Scope

Included features:

- Photo identification with AI suggestions checked against CIMA, the official Spanish medicine information service from AEMPS.
- Official medicine uses in English, when available.
- A personal cabinet with manual entry, search, sorting, editing and deletion.

Outside the scope:

- Reminders, dose tracking, shared cabinets, family accounts and cloud backup or sync.
- Diagnosis, treatment advice, dose or schedule calculation, drug interaction checks and international medicine equivalents.
- Full leaflet analysis, identification from paper leaflets and saved identification history.

## 3. Functional requirements

### Navigation

- Open the cabinet at startup and provide access to identification and manual entry, with Android Back support.
- Ask before leaving a form with unsaved changes. Offer to keep editing or discard them.

### Personal medicine cabinet

- List medicines with available photos, names, strengths, forms and saved reasons. Indicate missing names or photos.
- Search saved names and reasons while typing. Show newest records first and offer alphabetical sorting.
- View saved medication details.
- Show clear messages for empty cabinets and searches with no results.

### Medication entry and management

- Allow manual entry without AI or CIMA. Fields are optional, but a record needs at least one valid value.
- Allow users to save their own treatment instructions, reasons, dates and notes.
- Allow editing and photo changes without starting identification. Warn about duplicate names, but allow separate records.
- Ask for confirmation before deleting a record and its photo.

### Medication identification

- Show a live camera preview and start identification by taking a photo in one action. Read visible names, strengths, forms and national codes without guessing missing details.
- Confirm matches through CIMA using the available medication information, including the national code when available. A similar name alone is not enough for automatic confirmation. If several matches are possible, let the user choose before checking the selection.
- Let users read results without saving. Choosing to save opens a form with available photo and medicine details; nothing is saved automatically.

### Official medication information

- Show official uses only after CIMA confirmation. English labels must keep the source meaning and restrictions. Omit uses that cannot be processed reliably.
- If CIMA confirms the medication but loading or translating its official uses fails, keep the medication confirmed and allow retry when possible.
- Leave all official uses unselected by default. Save only user-selected uses and written reasons. Never generate personal treatment instructions.

### Error handling and recovery

- Clearly distinguish unidentified medications, unconfirmed matches, connection errors and timeouts.
- Explain camera problems and keep manual entry available. After failed identification, offer another photo or manual entry with available details, without official uses.
- Offer retries for temporary errors or when no medicine is identified. Reuse the photo and completed work when available.
- Show when identification is running, allow cancellation and ignore late results. Ask before switching main sections during identification.
- Keep entered values after failed saves. Explain storage errors and report success only after an action finishes.

## 4. Non-functional requirements

| Area | Requirement |
| --- | --- |
| Usability | Use clear English and easy-to-find actions. Support larger text settings on Android phones. |
| Performance | Limit service processing to 40 seconds and app waiting time to 45 seconds per request. Search results should update within 0.5 seconds for up to 100 records. |
| Security | Use HTTPS for online communication. Keep service secrets out of the Android app and public source code. |
| Privacy | Keep cabinet records local and do not upload them. OpenAI receives photos and official text for English use labels. CIMA receives medicine information, not photos. The backend must not keep permanent photos or identification history. |
| Reliability | Keep saved information after restarting the app. Failed saves, edits or deletions must leave stored records unchanged. |
| Offline use | Allow cabinet viewing, search, sorting, manual entry, editing and deletion without internet access. |
| Maintainability | Allow the main functions to be changed and tested separately. Document setup, checks and known limits. |

## 5. Constraints and limitations

- **Platform:** Android is the target platform. Camera access requires permission.
- **Online services:** Identification and official information need internet access and working external services.
- **AI:** Small text, blur, reflections or missing package details can cause wrong or uncertain suggestions.
- **CIMA:** Confirmation depends on available Spanish medicine records and sufficient, consistent medication information.
- **Photos:** Identification photos are limited to 15 MB.
- **Data protection:** There are no user accounts, separate app lock or added encryption for saved records. Protection depends on the device and Android storage. External services apply their own data policies.
- **Medical safety:** A CIMA data match does not confirm that a medicine is suitable for the user. Users must check the package and follow professional medical instructions.
