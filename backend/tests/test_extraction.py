from intel_platform.services.extraction import extract_entities_nlp


def test_extract_persons():
    text = "John Smith met with Jane Doe in Washington to discuss the operation."
    entities, relationships = extract_entities_nlp(text, doc_id="doc-1")
    person_names = [e["name"] for e in entities if e["entity_type"] == "Person"]
    assert "John Smith" in person_names


def test_extract_locations():
    text = "The attack originated from servers in Moscow and targeted offices in Berlin."
    entities, _ = extract_entities_nlp(text, doc_id="doc-1")
    location_names = [e["name"] for e in entities if e["entity_type"] == "Location"]
    assert len(location_names) >= 1


def test_extract_organizations():
    text = "Microsoft reported that APT-29 compromised several government agencies."
    entities, _ = extract_entities_nlp(text, doc_id="doc-1")
    org_names = [e["name"] for e in entities if e["entity_type"] == "Organization"]
    assert "Microsoft" in org_names


def test_extract_deduplicates():
    text = "John Smith went to the store. John Smith then went home."
    entities, _ = extract_entities_nlp(text, doc_id="doc-1")
    john_count = sum(1 for e in entities if e["name"] == "John Smith")
    assert john_count == 1


def test_extract_empty_text():
    entities, relationships = extract_entities_nlp("", doc_id="doc-1")
    assert entities == []
    assert relationships == []


# --- refang + URL/Email observables (Phase 1) -------------------------------

def test_extract_defanged_ip():
    text = "The C2 beacon reached out to 1.2.3[.]4 during the intrusion."
    entities, _ = extract_entities_nlp(text, doc_id="doc-1")
    ips = [e["name"] for e in entities if e["entity_type"] == "IPAddress"]
    assert "1.2.3.4" in ips


def test_extract_defanged_domain():
    text = "Beaconing traffic resolved to evil[.]com over the weekend."
    entities, _ = extract_entities_nlp(text, doc_id="doc-1")
    domains = [e["name"] for e in entities if e["entity_type"] == "Domain"]
    assert "evil.com" in domains


def test_extract_url_observable():
    text = "The dropper pulled its payload from hxxp://evil[.]com/malware.exe here."
    entities, _ = extract_entities_nlp(text, doc_id="doc-1")
    urls = [e["name"] for e in entities if e["entity_type"] == "URL"]
    assert "http://evil.com/malware.exe" in urls


def test_extract_email_observable():
    text = "Victims were told to contact admin@evil.com for the decryption key."
    entities, _ = extract_entities_nlp(text, doc_id="doc-1")
    emails = [e["name"] for e in entities if e["entity_type"] == "EmailAddress"]
    assert "admin@evil.com" in emails
