from neo4j import Driver

CONSTRAINTS = [
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Person) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT org_id IF NOT EXISTS FOR (n:Organization) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT loc_id IF NOT EXISTS FOR (n:Location) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT event_id IF NOT EXISTS FOR (n:Event) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT ip_id IF NOT EXISTS FOR (n:IPAddress) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT domain_id IF NOT EXISTS FOR (n:Domain) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT hash_id IF NOT EXISTS FOR (n:Hash) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT vuln_id IF NOT EXISTS FOR (n:Vulnerability) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT ttp_id IF NOT EXISTS FOR (n:TTP) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT malware_id IF NOT EXISTS FOR (n:Malware) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT actor_id IF NOT EXISTS FOR (n:ThreatActor) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT campaign_id IF NOT EXISTS FOR (n:Campaign) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT doc_id IF NOT EXISTS FOR (n:Document) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT topic_id IF NOT EXISTS FOR (n:Topic) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT report_id IF NOT EXISTS FOR (n:Report) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT assessment_id IF NOT EXISTS FOR (n:Assessment) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT project_id IF NOT EXISTS FOR (n:Project) REQUIRE n.id IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX entity_project IF NOT EXISTS FOR (n:Person) ON (n.project_id)",
    "CREATE INDEX org_project IF NOT EXISTS FOR (n:Organization) ON (n.project_id)",
    "CREATE INDEX ip_project IF NOT EXISTS FOR (n:IPAddress) ON (n.project_id)",
    "CREATE INDEX domain_project IF NOT EXISTS FOR (n:Domain) ON (n.project_id)",
    "CREATE INDEX actor_project IF NOT EXISTS FOR (n:ThreatActor) ON (n.project_id)",
    "CREATE INDEX doc_project IF NOT EXISTS FOR (n:Document) ON (n.project_id)",
]

FULLTEXT_INDEXES = [
    """CREATE FULLTEXT INDEX entity_name_search IF NOT EXISTS
       FOR (n:Person|Organization|ThreatActor|Domain|IPAddress|Malware|Campaign|Location|Event|Hash|Vulnerability|TTP|Topic|Report|Assessment)
       ON EACH [n.name]""",
]


def initialize_schema(driver: Driver) -> None:
    with driver.session() as session:
        for stmt in CONSTRAINTS + INDEXES:
            session.run(stmt)
        for stmt in FULLTEXT_INDEXES:
            try:
                session.run(stmt)
            except Exception:
                pass
