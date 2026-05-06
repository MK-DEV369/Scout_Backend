from neo4j import GraphDatabase

from app.core.config import settings

class GraphService:
    def __init__(self) -> None:
        self._driver = None
        self._database = settings.neo4j_database
        if settings.neo4j_uri and settings.neo4j_user and settings.neo4j_password:
            self._driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
            self._ensure_indexes()

    @property
    def enabled(self) -> bool:
        return self._driver is not None

    @property
    def driver(self):
        return self._driver

    @property
    def database(self) -> str | None:
        return self._database

    def _ensure_indexes(self) -> None:
        if not self._driver:
            return

        statements = [
            "CREATE INDEX risk_event_id_index IF NOT EXISTS FOR (e:RiskEvent) ON (e.event_id)",
            "CREATE INDEX supplier_id_index IF NOT EXISTS FOR (s:Supplier) ON (s.supplier_id)",
            "CREATE INDEX manufacturer_id_index IF NOT EXISTS FOR (m:Manufacturer) ON (m.manufacturer_id)",
        ]
        with self._driver.session(database=self._database) as session:
            for stmt in statements:
                session.run(stmt)

    def upsert_risk_paths_batch(self, rows: list[dict]) -> None:
        if not self._driver or not rows:
            return

        query = """
        UNWIND $rows AS row
        MERGE (e:RiskEvent {event_id: row.event_id})
        SET e.event_type = row.event_type,
            e.severity = row.severity,
            e.timestamp = row.timestamp,
            e.headline = row.headline,
            e.base_risk_score = row.base_risk_score,
            e.composite_risk_score = row.composite_risk_score

        FOREACH (_ IN CASE WHEN row.country IS NULL THEN [] ELSE [1] END |
            MERGE (c:Country {name: row.country})
            MERGE (e)-[ac:AFFECTS_COUNTRY]->(c)
            SET ac.impact_weight = coalesce(row.affects_country_weight, 0.7)
        )
        FOREACH (_ IN CASE WHEN row.port IS NULL THEN [] ELSE [1] END |
            MERGE (p:Port {name: row.port})
            MERGE (e)-[ap:AFFECTS_PORT]->(p)
            SET ap.impact_weight = coalesce(row.affects_port_weight, 0.9)
        )
        FOREACH (_ IN CASE WHEN row.commodity IS NULL THEN [] ELSE [1] END |
            MERGE (co:Commodity {name: row.commodity})
            MERGE (e)-[am:AFFECTS_COMMODITY]->(co)
            SET am.impact_weight = coalesce(row.affects_commodity_weight, 0.8)
        )

        FOREACH (_ IN CASE WHEN row.supplier_id IS NULL THEN [] ELSE [1] END |
            MERGE (s:Supplier {supplier_id: row.supplier_id})
            SET s.name = row.supplier_name,
                s.country = row.supplier_country,
                s.criticality = row.supplier_criticality

            FOREACH (_2 IN CASE WHEN row.country IS NULL THEN [] ELSE [1] END |
                MERGE (c2:Country {name: row.country})
                MERGE (s)-[li:LOCATED_IN]->(c2)
                SET li.impact_weight = coalesce(row.located_in_weight, 0.7)
            )
            FOREACH (_2 IN CASE WHEN row.port IS NULL THEN [] ELSE [1] END |
                MERGE (p2:Port {name: row.port})
                MERGE (s)-[st:SHIPS_THROUGH]->(p2)
                SET st.impact_weight = coalesce(row.ships_through_weight, 0.8)
            )
            FOREACH (_2 IN CASE WHEN row.commodity IS NULL THEN [] ELSE [1] END |
                MERGE (co2:Commodity {name: row.commodity})
                MERGE (s)-[pr:PROVIDES]->(co2)
                SET pr.impact_weight = coalesce(row.provides_weight, 0.8)
            )

            MERGE (m:Manufacturer {manufacturer_id: row.manufacturer_id})
            SET m.name = row.manufacturer_name
            MERGE (m)-[:MONITORS]->(s)

            MERGE (e)-[ex:EXPOSES]->(s)
            SET ex.risk_exposure_score = row.risk_exposure_score,
                ex.path_weight = row.path_weight,
                ex.updated_at = row.timestamp
        )
        """
        with self._driver.session(database=self._database) as session:
            session.run(query, rows=rows)

    def estimate_path_weight(self, *, event_id: int, supplier_id: int | None) -> float:
        if not self._driver or supplier_id is None:
            return 1.0

        query = """
        MATCH (e:RiskEvent {event_id: $event_id})
        MATCH (s:Supplier {supplier_id: $supplier_id})
        OPTIONAL MATCH p=(e)-[:AFFECTS_COUNTRY|AFFECTS_PORT|AFFECTS_COMMODITY*1..3]->(i)
        <-[:LOCATED_IN|SHIPS_THROUGH|PROVIDES]-(s)
        WITH p
        RETURN coalesce(max(reduce(w = 1.0, rel IN relationships(p) | w * coalesce(rel.impact_weight, 1.0))), 1.0) AS best_weight
        """
        with self._driver.session(database=self._database) as session:
            record = session.run(query, event_id=event_id, supplier_id=supplier_id).single()
            if not record:
                return 1.0
            return float(record.get("best_weight") or 1.0)

    def get_impact(self, *, event_id: int, manufacturer_id: str, limit: int = 25) -> list[dict]:
        if not self._driver:
            return []

        query = """
        MATCH (e:RiskEvent {event_id: $event_id})
        MATCH (m:Manufacturer {manufacturer_id: $manufacturer_id})-[:MONITORS]->(s:Supplier)
        OPTIONAL MATCH p=(e)-[:AFFECTS_COUNTRY|AFFECTS_PORT|AFFECTS_COMMODITY*1..3]->(i)
        <-[:LOCATED_IN|SHIPS_THROUGH|PROVIDES]-(s)
        WITH e, s, p,
             coalesce(reduce(w = 1.0, rel IN relationships(p) | w * coalesce(rel.impact_weight, 1.0)), 0.0) AS path_weight,
             [rel IN relationships(p) | type(rel)] AS path_types
        RETURN
            e.event_id AS event_id,
            e.event_type AS event_type,
            e.composite_risk_score AS composite_risk_score,
            s.supplier_id AS supplier_id,
            s.name AS supplier_name,
            s.criticality AS supplier_criticality,
            path_types,
            path_weight
        ORDER BY path_weight DESC, e.composite_risk_score DESC
        LIMIT $limit
        """
        with self._driver.session(database=self._database) as session:
            rows = session.run(
                query,
                event_id=event_id,
                manufacturer_id=manufacturer_id,
                limit=limit,
            ).data()

            if not rows:
                fallback_query = """
                MATCH (e:RiskEvent {event_id: $event_id})
                OPTIONAL MATCH p=(e)-[:AFFECTS_COUNTRY|AFFECTS_PORT|AFFECTS_COMMODITY*1..3]->(i)
                <-[:LOCATED_IN|SHIPS_THROUGH|PROVIDES]-(s:Supplier)
                WITH e, s, p,
                     coalesce(reduce(w = 1.0, rel IN relationships(p) | w * coalesce(rel.impact_weight, 1.0)), 0.0) AS path_weight,
                     [rel IN relationships(p) | type(rel)] AS path_types
                RETURN
                    e.event_id AS event_id,
                    e.event_type AS event_type,
                    e.composite_risk_score AS composite_risk_score,
                    s.supplier_id AS supplier_id,
                    s.name AS supplier_name,
                    s.criticality AS supplier_criticality,
                    path_types,
                    path_weight
                ORDER BY path_weight DESC, e.composite_risk_score DESC
                LIMIT $limit
                """
                rows = session.run(fallback_query, event_id=event_id, limit=limit).data()

            if not rows:
                event_only = session.run(
                    "MATCH (e:RiskEvent {event_id: $event_id}) RETURN e.event_id AS event_id, e.event_type AS event_type, e.composite_risk_score AS composite_risk_score",
                    event_id=event_id,
                ).single()
                if event_only:
                    rows = [
                        {
                            "event_id": event_only.get("event_id"),
                            "event_type": event_only.get("event_type"),
                            "composite_risk_score": event_only.get("composite_risk_score"),
                            "supplier_id": None,
                            "supplier_name": "unmapped_supplier",
                            "supplier_criticality": None,
                            "path_types": [],
                            "path_weight": 0.0,
                        }
                    ]

        payload = []
        for row in rows:
            path_types = row.get("path_types") or []
            explanation = "No exposure path found"
            if path_types:
                explanation = " -> ".join(path_types)
            payload.append(
                {
                    "event_id": row.get("event_id"),
                    "event_type": row.get("event_type"),
                    "supplier_id": row.get("supplier_id"),
                    "supplier": row.get("supplier_name"),
                    "risk": row.get("composite_risk_score"),
                    "path_weight": row.get("path_weight"),
                    "path": path_types,
                    "explanation": explanation,
                }
            )
        if not payload:
            payload.append(
                {
                    "event_id": event_id,
                    "event_type": "unknown",
                    "supplier_id": None,
                    "supplier": "unmapped_supplier",
                    "risk": None,
                    "path_weight": 0.0,
                    "path": [],
                    "explanation": "No graph path is materialized yet for this event id",
                }
            )
        return payload

    def get_supplier_risk(self, *, supplier_id: int, limit: int = 10) -> dict:
        if not self._driver:
            return {"summary": {}, "events": []}

        summary_query = """
        MATCH (s:Supplier {supplier_id: $supplier_id})
        OPTIONAL MATCH (e:RiskEvent)-[x:EXPOSES]->(s)
        RETURN
            s.supplier_id AS supplier_id,
            s.name AS supplier_name,
            s.country AS country,
            s.criticality AS criticality,
            count(e) AS exposure_count,
            coalesce(max(x.risk_exposure_score), 0.0) AS max_exposure,
            coalesce(avg(x.risk_exposure_score), 0.0) AS avg_exposure
        """
        events_query = """
        MATCH (s:Supplier {supplier_id: $supplier_id})<-[x:EXPOSES]-(e:RiskEvent)
        RETURN
            e.event_id AS event_id,
            e.event_type AS event_type,
            e.headline AS headline,
            e.composite_risk_score AS composite_risk_score,
            x.risk_exposure_score AS risk_exposure_score,
            x.path_weight AS path_weight
        ORDER BY x.risk_exposure_score DESC
        LIMIT $limit
        """
        with self._driver.session(database=self._database) as session:
            summary = session.run(summary_query, supplier_id=supplier_id).single()
            events = session.run(events_query, supplier_id=supplier_id, limit=limit).data()

        return {
            "summary": dict(summary) if summary else {},
            "events": events,
        }

    def get_graph_summary(self) -> dict:
        if not self._driver:
            return {
                "enabled": False,
                "node_count": 0,
                "relationship_count": 0,
                "labels": [],
                "relationship_types": [],
            }

        with self._driver.session(database=self._database) as session:
            node_count = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            rel_count = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            labels = session.run(
                "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS count ORDER BY count DESC"
            ).data()
            relationship_types = session.run(
                "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY count DESC"
            ).data()

        return {
            "enabled": True,
            "node_count": int(node_count),
            "relationship_count": int(rel_count),
            "labels": labels,
            "relationship_types": relationship_types,
        }

    def upsert_event_path(
        self,
        *,
        event_id: int,
        event_category: str,
        country: str | None,
        supplier_name: str | None,
        manufacturer_name: str | None,
        commodity: str | None,
    ) -> None:
        self.upsert_risk_paths_batch(
            [
                {
                    "event_id": event_id,
                    "event_type": event_category,
                    "severity": 0.5,
                    "timestamp": "",
                    "headline": event_category,
                    "base_risk_score": 0.5,
                    "composite_risk_score": 0.5,
                    "country": country,
                    "port": None,
                    "commodity": commodity,
                    "supplier_id": None,
                    "supplier_name": supplier_name,
                    "supplier_country": country,
                    "supplier_criticality": 1.0,
                    "manufacturer_id": "default_manufacturer",
                    "manufacturer_name": manufacturer_name,
                    "risk_exposure_score": 0.5,
                    "path_weight": 1.0,
                }
            ]
        )


graph_service = GraphService()
