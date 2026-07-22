# MITRE ATT&CK® Attribution

© 2026 The MITRE Corporation. This work is reproduced and distributed with the permission of The MITRE Corporation.

This platform ingests and displays data from MITRE ATT&CK® (the Enterprise
STIX 2.1 dataset, `mitre-attack/attack-stix-data`), used under the ATT&CK Terms
of Use. ATT&CK® is a registered trademark of The MITRE Corporation.

The dataset itself (~50 MB) is fetched on demand at ingest time and cached
locally under `data/attack/` — it is **not** committed to this repository.

## MITRE CWE™ and CAPEC™ Attribution

For the CVE→ATT&CK chain (Phase 3a), this platform also ingests MITRE CWE™
(`cwec_latest.xml.zip`) and MITRE CAPEC™ (`capec_latest.xml`), used under the
MITRE Terms of Use. CWE™ (Common Weakness Enumeration) and CAPEC™ (Common Attack
Pattern Enumeration and Classification) are trademarks of The MITRE Corporation.

Copyright © 2006–2026, The MITRE Corporation. CWE and CAPEC and the CWE and CAPEC
logos are trademarks of The MITRE Corporation.

Both files are keyless and redistributable; like the ATT&CK bundle they are
fetched on demand and cached locally under `data/attack/` (gitignored) — **not**
committed to this repository.
