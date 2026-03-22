# Intelligence Platform — Test Use Cases

## Use Case 1: OSINT Cyber Threat Investigation
**Persona:** Cyber threat analyst investigating a ransomware campaign
**Flow:** Create project → Ingest multiple threat reports → Analyze entity network → Generate threat assessment → Produce INTSUM

## Use Case 2: Multi-Source Document Exploitation
**Persona:** All-source analyst processing batch documents
**Flow:** Create project → Batch upload 3+ documents (different formats) → Review extracted entities → Verify entity resolution (deduplication) → Check network statistics

## Use Case 3: Collection-Driven OSINT Workflow
**Persona:** OSINT collector tasked with a PIR
**Flow:** Create project → Submit PIR → Create collection task → Manually upload documents matching the PIR → Review sources in Data Sources → Query graph for answers

## Use Case 4: Entity Assessment & Hypothesis Testing
**Persona:** Intelligence analyst evaluating threat actor attribution
**Flow:** Ingest conflicting reports → View entity relationships → Create assessments with probability ratings → Use ACH (hypothesis generation skill) → Review assessment in graph

## Use Case 5: Network Analysis & Community Detection
**Persona:** Network analyst looking for hidden connections
**Flow:** Ingest interconnected documents → View graph visualization → Run community detection → Check network statistics → Find shortest paths → Identify key nodes by centrality

## Use Case 6: Intelligence Product Generation
**Persona:** Report writer producing deliverables
**Flow:** Select entities for report → Choose report type → Generate with LLM → Review evidence chains → Export
