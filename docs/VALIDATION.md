# MedClue validation

Validation date: 17 November 2026.

## 1. Validation approach

MedClue was tested using automated Python tests, manual checks on an Android phone, real medication package photos, and a review of the code and cloud configuration. This document reports the results and the limits of these checks.

## 2. Automated testing

Both test suites were run on Windows with Python 3.12.10 and pytest 9.2.0.

| Suite | Passed | Failed | Skipped | Time |
| --- | ---: | ---: | ---: | ---: |
| Backend | 486 | 0 | 0 | 7.52 s |
| Frontend | 579 | 0 | 0 | 8.87 s |
| **Total** | **1,065** | **0** | **0** | **16.39 s** |

To run the tests from the repository root in PowerShell using the configured virtual environment:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest -o pythonpath=src tests -q
Set-Location ..\frontend
..\.venv\Scripts\python.exe -m pytest tests -q
```

The tests cover medication management, SQLite operations, forms, navigation, photo handling, API communication, identification, CIMA matching, errors, retries and cancellation. Storage failure tests check that existing records and form values are preserved. The tests also check that conflicting medicine details prevent automatic confirmation during name-based matching.

Timeout tests use shorter delays to check the timeout and retry logic. The backend tests also check the configured 40-second limit. Photo tests cover empty or invalid captures, size limits and unsupported media types.

## 3. Acceptance testing

The following checks were performed manually on Android. Automated tests complement the manual checks for failures and other conditions that are difficult to reproduce on a phone.

| Test | Area | Manual result |
| --- | --- | --- |
| AT-01 | Startup and navigation | Pass |
| AT-02 | Cabinet and medication details | Pass |
| AT-03 | Search and sorting | Pass |
| AT-04 | Empty cabinet | Pass |
| AT-05 | Manual entry and photos | Pass |
| AT-06 | Personal instructions and reasons | Pass |
| AT-07 | Saving and duplicate handling | Pass |
| AT-08 | Editing medication records | Pass |
| AT-09 | Unsaved changes | Pass |
| AT-10 | Deletion and confirmation | Pass |
| AT-11 | Camera, capture and cancellation | Pass |
| AT-12 | Confirmed identification results | Pass |
| AT-13 | Multiple matches and unidentified medications | Pass |
| AT-14 | Unconfirmed results and connection errors | Pass |
| AT-15 | Navigation and cancellation during identification | Pass |
| AT-16 | Saving an identified medication | Pass |

All manual checks passed as reported by the tester. The manual results do not imply that every error condition or timing limit was reproduced on Android. Storage failures, invalid photo requests and timeout recovery were also checked through automated tests, with the coverage limits described above.

## 4. AI identification evaluation

The local backend was tested with 30 package photos using real OpenAI and CIMA requests. The sample included different medicines, repeated medicines photographed under different conditions, images with and without a readable national code, and products that could not be confirmed. Each response was recorded in JSON with the AI output, backend result and response time.

| Result | Photos | Percentage |
| --- | ---: | ---: |
| Confirmed | 20 | 66.7% |
| Multiple matches | 5 | 16.7% |
| Unconfirmed (no match) | 4 | 13.3% |
| Not identified | 1 | 3.3% |
| **Total** | **30** | **100%** |

Of the 20 confirmed results, 17 were resolved using the national code extracted by AI and 3 through name-based matching. All 17 extracted codes matched the returned CIMA codes after normalization. The 5 multiple-match results included 4 AI candidate lists and 1 CIMA presentation list. In the latter case, an additional pharmaceutical form was offered for review rather than confirmed automatically.

All 30 results were reported to match the tester's expectations. No incorrect automatic medicine identification was reported. This is an observed result for this sample, not an independent accuracy measurement for all medicines. The returned codes were compared with the AI output. Name-based matching can return an equivalent presentation without identifying the exact package size.

No unconfirmed result included official uses. All 30 requests returned HTTP 200 without a connection error or timeout. Multiple-match requests were measured up to the initial list of options, without the subsequent user selection.

## 5. Official uses validation

Section 4.1 (Therapeutic indications) of 16 CIMA medicine records was compared with 106 English use labels across the 20 confirmed results. The comparison did not identify any new therapeutic indication that was absent from the corresponding source. Some labels could express the original conditions more precisely:

- Ibuprofeno Cinfamed: the wording of the age restriction is ambiguous.
- Algidol: one result does not explicitly identify codeine in the pediatric indication.
- Prednisona Cinfa: the combination chemotherapy context may not be clear in every individual label in the relevant group of indications.

The labels generally kept the meaning of the source, but the review does not guarantee that all qualifications are preserved in every future result. This is a comparison with the source text, not clinical validation. The app does not provide personal treatment recommendations.

## 6. Performance

### Identification

The 30 requests in the AI evaluation produced the following response times:

| Measurement | Time |
| --- | ---: |
| Minimum | 4.19 s |
| Mean | 10.79 s |
| Maximum | 26.14 s |

All 30 requests completed within 40 seconds. The measurements include the local backend processing and real calls to OpenAI and CIMA, including use translation where applicable. They do not include Android camera capture, communication with the deployed backend or screen rendering.

### Cabinet search

A temporary SQLite database with 100 fictional medication records without photos was used on Windows. All 20 searches, 10 by name and 10 by reason, returned the expected records.

| Measurement | Time |
| --- | ---: |
| Minimum | 1.080 ms |
| Mean | 1.431 ms |
| Maximum | 3.898 ms |
| Target | 500 ms |

The measurement includes database reading, record reconstruction, filtering and sorting. All searches were below the target. Android rendering and search performance with 100 records containing photos were not measured.

## 7. Offline use and data persistence

Manual Android checks confirmed that cabinet viewing, search, sorting, manual entry with photos, editing and deletion work without an internet connection. Saved information and photos remained available after restarting the app and installing an updated APK without uninstalling the existing app. Identification worked again after restoring the connection.

## 8. Security and privacy

The review covered the source code, the local APK application archive and the active Cloud Run configuration.

| Check | Result |
| --- | --- |
| HTTPS | Pass: the public endpoint responded over HTTPS with certificate validation; the reviewed external service configuration uses HTTPS. |
| Service secrets | Pass: both backend secrets are linked to Secret Manager. |
| Secrets in source and APK | No obvious credentials found in the reviewed files and local APK archive. |
| Local cabinet storage | Pass: records and saved photos are stored in SQLite without cloud synchronization. |
| External data | Personal cabinet fields are not uploaded. Identification photos are sent with their original bytes, which may include metadata. |
| Backend photo storage | Pass: no permanent photo storage is implemented. |
| OpenAI requests | Pass: both AI operations set `store=False`. |
| Retry tokens | Pass: signed tokens expire after 15 minutes. They are not encrypted. |
| Cloud logs | No evidence of exposed secrets, photos, retry tokens or cabinet content was found in the inspected logs. |

A total of 757 Cloud Run log entries were reviewed. No credentials, medication photos, retry tokens or personal cabinet data were detected in the reviewed logs.

## 9. Estimated AI cost

The OpenAI usage dashboard showed a cumulative project cost of USD 0.97 for 271 requests and 684,811 tokens. The average cost was approximately USD 0.00358 per AI request.

The evaluation of 30 photos is estimated to have used 30 image analysis requests and 20 translation requests. Using the historical average cost:

| Item | Estimated cost (USD) |
| --- | ---: |
| 30-photo evaluation | 0.18 |
| Average identification per photo | 0.006 |
| 100 photo identifications | 0.60 |
| 1,000 photo identifications | 5.97 |

These are estimates, not measured costs for individual identification requests. Actual costs depend on image and text token usage, the number of AI calls and retries. Cloud hosting costs are not included.

## 10. Conclusion and limitations

The automated tests and manual Android checks produced satisfactory results for the main MVP features. The real-service evaluation also demonstrated medication identification, uncertain results and official use retrieval within the observed response times.

The evaluation is limited to a small photo sample and one manually tested Android device. Users should photograph one medication at a time, check the result against the package and not rely on AI output for treatment decisions. Identification requires an active backend and external services, while cabinet operations remain available offline.

The remaining verification limits are described in the relevant sections. These results support the MVP scope but do not establish clinical accuracy, performance on every device or comprehensive security. Installation instructions and public demo restrictions are described in [DEPLOYMENT.md](DEPLOYMENT.md).
