from intel_platform.graph.schema import initialize_schema


def test_initialize_schema(neo4j_driver):
    initialize_schema(neo4j_driver)
    with neo4j_driver.session() as session:
        result = session.run("SHOW CONSTRAINTS")
        constraints = list(result)
        assert len(constraints) > 0
