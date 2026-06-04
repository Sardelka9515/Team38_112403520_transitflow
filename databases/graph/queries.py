"""
TransitFlow — Neo4j 圖資料庫查詢層
=================================

本模組提供 TransitFlow AI 助理可呼叫的 Neo4j graph query functions。
這些函數主要處理路網拓樸問題，例如路線搜尋、轉乘、替代路線、
延誤影響範圍與直接相鄰站點。

工具選擇原則：
- query_shortest_route:
    使用者問最快路線、最短時間、quickest route、fastest route,
    或一般「如何從 A 到 B」且沒有指定票價、避開站點或延誤影響時使用。

- query_cheapest_route:
    使用者問最便宜路線、最低票價、lowest fare、cheapest way,
    或以費用最小化為主要目標時使用。

- query_alternative_routes:
    使用者問替代路線、避開某站、某站關閉、某站延誤、disruption、
    closure、avoid station 或 route around problem 時使用。

- query_interchange_path:
    使用者明確詢問 metro 與 national rail 之間的轉乘、interchange、
    transfer,或需要解釋在哪裡從一種交通網路換到另一種時使用。

- query_delay_ripple:
    使用者問某站延誤或中斷會影響哪些附近站點、影響範圍、
    ripple effect、affected stations 或 N hops 內站點時使用。
    這不是路線規劃工具，而是路網影響分析工具。

- query_station_connections:
    使用者問某站有哪些直接相鄰站、direct connections、adjacent stations、
    nearby stations 或該站有哪些直接轉乘/連線時使用。
    這只查一跳連線，不計算完整路線。

站點 ID 規則：
- Metro station ID 以 "MS" 開頭，例如 "MS01"。
- National rail station ID 以 "NR" 開頭，例如 "NR01"。
"""

from __future__ import annotations

from typing import Optional

from neo4j import GraphDatabase

from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


def _driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def example_count_nodes() :
    """
    範例函數：計算目前 Neo4j graph 中的所有節點數量。

    注意：
        這個函數主要用於開發、測試與確認 Neo4j 是否成功連線。
        它不是 TransitFlow AI agent 的正式查詢工具。
        使用者若詢問路線、轉乘、票價、延誤影響或站點連線，不應呼叫此函數。

    適合使用：
        - 開發者想快速確認 Neo4j 是否有資料。
        - 測試資料是否已經成功 seed 進 graph database。

    不適合使用：
        - 不適合回答任何路線規劃問題。
        - 不適合回答最快路線、最便宜路線、替代路線、轉乘或延誤影響問題。

    回傳：
        int,目前 graph 中所有 nodes 的總數。
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) AS total")
            return result.single()["total"]

def _relationship_pattern(network: str, origin_id: str = "", destination_id: str = "") :
    """
    根據指定 network 與起訖站 ID,回傳安全的 Cypher relationship type pattern。

    注意：
        這是內部輔助函數，不是給 AI agent 或使用者直接呼叫的工具。
        因為 Cypher relationship type 無法用參數化方式傳入，所以本函數只回傳
        程式內固定允許的 relationship types,避免把任意使用者輸入直接插入 Cypher。

    network 規則：
        - "metro":
            只允許 METRO_LINK,適合 metro 站點之間的路線。
        - "rail":
            只允許 RAIL_LINK,適合 national rail 站點之間的路線。
        - "auto":
            若 origin_id 和 destination_id 都以 "MS" 開頭，只使用 METRO_LINK。
            若 origin_id 和 destination_id 都以 "NR" 開頭，只使用 RAIL_LINK。
            若起訖站分屬不同網路，允許 METRO_LINK、RAIL_LINK 與 INTERCHANGE_TO,
            讓路線可以跨 metro 與 national rail 轉乘。
        - 其他值：
            為了保持可用性，預設允許 METRO_LINK、RAIL_LINK 與 INTERCHANGE_TO。

    參數：
        network:
            搜尋網路範圍，建議使用 "metro"、"rail" 或 "auto"。
        origin_id:
            起點站 ID,例如 "MS01" 或 "NR01"。
        destination_id:
            終點站 ID,例如 "MS09" 或 "NR05"。

    回傳：
        str,可安全插入 Cypher relationship pattern 的 relationship type 字串。
        例如 "METRO_LINK"、"RAIL_LINK" 或 "METRO_LINK|RAIL_LINK|INTERCHANGE_TO"。
    """
    network = (network or "auto").lower()

    if network == "metro":
        return "METRO_LINK"

    if network == "rail":
        return "RAIL_LINK"

    if network == "auto":
        if origin_id.startswith("MS") and destination_id.startswith("MS"):
            return "METRO_LINK"
        if origin_id.startswith("NR") and destination_id.startswith("NR"):
            return "RAIL_LINK"
        return "METRO_LINK|RAIL_LINK|INTERCHANGE_TO"

    return "METRO_LINK|RAIL_LINK|INTERCHANGE_TO"


def query_station_connections(station_id: str) :
    """
    查詢某一站的一跳直接連線站點。

    用途：
        回傳指定站點直接相鄰的 metro、national rail 或 interchange 連線。
        本函數只查詢「直接連到的站」，不會計算從起點到終點的完整路線，
        也不會做最快路線、最便宜路線或替代路線搜尋。

    適合使用：
        - 使用者詢問某站直接連到哪些站。
        - 使用者詢問某站的 adjacent stations、nearby stations 或 direct connections。
        - 使用者詢問某站有哪些可用 line、直接轉乘或一跳鄰居。
        - 使用者想了解某一站在 graph network 中的直接連線關係。
        - 使用者問「MS01 附近直接有哪些站」或「NR03 直接連到誰」。

    不適合使用：
        - 若使用者詢問從 A 到 B 的最快路線，請改用 query_shortest_route。
        - 若使用者詢問從 A 到 B 的最便宜路線，請改用 query_cheapest_route。
        - 若使用者詢問避開某站、封站、延誤繞路或替代路線，
          請改用 query_alternative_routes。
        - 若使用者詢問 metro 與 national rail 之間的完整轉乘路徑，
          請改用 query_interchange_path。
        - 若使用者詢問某站延誤會影響哪些站，
          請改用 query_delay_ripple。

    參數：
        station_id:
            要查詢直接連線的站點 ID。
            Metro station ID 以 "MS" 開頭，例如 "MS01"。
            National rail station ID 以 "NR" 開頭，例如 "NR01"。

    回傳：
        list[dict]，每個 dict 代表一條從該站出發的一跳直接連線，包含：
        - from_id: 查詢站點 ID。
        - from_name: 查詢站點名稱。
        - relationship_type: 連線類型，例如 METRO_LINK、RAIL_LINK 或 INTERCHANGE_TO。
        - line: metro 或 rail line 名稱；若是 INTERCHANGE_TO 可能為 None。
        - travel_time_min: 此直接連線的預估時間，單位為分鐘。
        - fare_usd: 此直接連線的估計費用；若是轉乘步行通常為 0。
        - to_id: 相鄰站點 ID。
        - to_name: 相鄰站點名稱。
        - to_labels: 相鄰站點的 Neo4j labels。

    範例使用情境：
        使用者問:「MS01 直接連到哪些站?」
        使用者問:「Central Square 附近有哪些直接相鄰站?」
        使用者問:「NR03 有哪些 direct connections?」
    """
    cypher = """
    MATCH (s {station_id: $station_id})-[r]->(n)
    RETURN
        s.station_id AS from_id,
        s.name AS from_name,
        type(r) AS relationship_type,
        r.line AS line,
        coalesce(r.travel_time_min, r.walk_time_min, 0) AS travel_time_min,
        coalesce(r.fare_usd, r.fare_standard, 0) AS fare_usd,
        n.station_id AS to_id,
        n.name AS to_name,
        labels(n) AS to_labels
    ORDER BY relationship_type, line, to_id
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(cypher, station_id=station_id)
            return [dict(record) for record in result]


def query_shortest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
) :
    """
    用途：
        查詢兩個站點之間「總旅行時間最短」的路線。

    適合使用：
        - 使用者詢問最快路線、最短時間路線、quickest route、fastest route。
        - 使用者問「如何從 A 到 B」且沒有特別指定要最便宜、避開某站或查看延誤影響。
        - 可處理 metro 內部路線、national rail 內部路線，也可在 network="auto"
          時處理跨 metro / national rail 的路線。

    不適合使用：
        - 若使用者詢問最便宜、最低票價、lowest fare、cheapest route,
          請改用 query_cheapest_route。
        - 若使用者詢問避開某站、封站、延誤繞路、alternative route,
          請改用 query_alternative_routes。
        - 若使用者主要想知道某站延誤會影響哪些站，
          請改用 query_delay_ripple。
        - 若使用者只問某站直接連到哪些站，
          請改用 query_station_connections。
        - 若使用者明確強調轉乘點或 interchange 說明，
          請優先考慮 query_interchange_path。

    參數：
        origin_id:
            起點站 ID。Metro station 使用 "MS" 開頭，例如 "MS01";
            National rail station 使用 "NR" 開頭，例如 "NR01"。
        destination_id:
            終點站 ID。格式同 origin_id,例如 "MS09" 或 "NR05"。
        network:
            搜尋範圍。
            - "metro"：只搜尋 metro network。
            - "rail"：只搜尋 national rail network。
            - "auto"：根據站點 ID 自動推斷；若起訖站分屬不同網路，允許使用 INTERCHANGE_TO 轉乘。

    回傳：
        dict,包含:
        - found: 是否找到路線。
        - origin_id, destination_id: 起訖站 ID。
        - total_time_min: 預估總旅行時間，單位為分鐘。
        - path: 依序排列的站點清單。
        - legs: 每一段路線的 from/to station、relationship_type、line 與 travel_time_min。
    """
    rel_pattern = _relationship_pattern(network, origin_id, destination_id)

    cypher = f"""
    MATCH path = (a {{station_id: $origin_id}})-[:{rel_pattern}*1..8]-(b {{station_id: $destination_id}})
    WHERE all(i IN range(0, size(nodes(path)) - 2)
              WHERE NOT nodes(path)[i] IN nodes(path)[i + 1..])
    WITH path,
         reduce(total = 0, r IN relationships(path) |
             total + coalesce(r.travel_time_min, r.walk_time_min, 0)
         ) AS total_time_min
    ORDER BY total_time_min ASC, length(path) ASC
    LIMIT 1
    RETURN
        total_time_min,
        [n IN nodes(path) | {{
            station_id: n.station_id,
            name: n.name,
            labels: labels(n)
        }}] AS stations,
        [i IN range(0, size(relationships(path)) - 1) | {{
            from_id: nodes(path)[i].station_id,
            from_name: nodes(path)[i].name,
            to_id: nodes(path)[i + 1].station_id,
            to_name: nodes(path)[i + 1].name,
            relationship_type: type(relationships(path)[i]),
            line: relationships(path)[i].line,
            travel_time_min: coalesce(
                relationships(path)[i].travel_time_min,
                relationships(path)[i].walk_time_min,
                0
            )
        }}] AS legs
    """

    with _driver() as driver:
        with driver.session() as session:
            record = session.run(
                cypher,
                origin_id=origin_id,
                destination_id=destination_id,
            ).single()

            if record is None:
                return {
                    "found": False,
                    "origin_id": origin_id,
                    "destination_id": destination_id,
                    "total_time_min": None,
                    "path": [],
                    "legs": [],
                }

            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "total_time_min": record["total_time_min"],
                "path": record["stations"],
                "legs": record["legs"],
            }


def query_cheapest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
    fare_class: str = "standard",
) :
    """
    查詢兩個站點之間「估計費用最低」的路線。

    用途：
        根據 Neo4j graph relationship 上的 fare_usd、fare_standard 或 fare_first,
        找出從起點到終點估計交通費用最低的路線。
        本函數重視「費用最低」，不是旅行時間最短。

    適合使用：
        - 使用者詢問最便宜路線、最低票價、cheapest route 或 lowest fare。
        - 使用者想比較從 A 到 B 哪條路線花費較少。
        - 使用者明確表示比起速度，更在意票價或費用。
        - 使用者詢問 standard 或 first class 的估計路線費用。

    不適合使用：
        - 若使用者詢問最快路線、最短時間、quickest route 或 fastest route,
          請改用 query_shortest_route。
        - 若使用者詢問避開某站、封站、延誤繞路或替代路線，
          請改用 query_alternative_routes。
        - 若使用者詢問某站延誤會影響哪些站，
          請改用 query_delay_ripple。
        - 若使用者只問某站直接連到哪些站，
          請改用 query_station_connections。
        - 若使用者要查詢實際訂票價格、座位價格、班次票價或 booking 資訊，
          不應使用本函數；本函數只提供 graph route 的估計費用。

    參數：
        origin_id:
            起點站 ID。
            Metro station ID 以 "MS" 開頭，例如 "MS01"。
            National rail station ID 以 "NR" 開頭，例如 "NR01"。
        destination_id:
            終點站 ID。
            格式同 origin_id,例如 "MS09" 或 "NR05"。
        network:
            搜尋網路範圍。
            - "metro"：只搜尋 metro network。
            - "rail"：只搜尋 national rail network。
            - "auto"：自動判斷搜尋範圍，必要時允許跨網路轉乘。
        fare_class:
            National rail 的票價等級。
            - "standard"：使用 fare_standard。
            - "first"：使用 fare_first。
            Metro links 使用 fare_usd。
            INTERCHANGE_TO 轉乘步行通常視為 0 元。

    回傳：
        dict,包含:
        - found: 是否找到路線。
        - origin_id: 起點站 ID。
        - destination_id: 終點站 ID。
        - fare_class: 使用的 rail fare class。
        - total_fare_usd: 預估總費用，單位為美元。
        - stations: 依序排列的站點清單。
        - legs: 每一段路線，包含 from/to station、relationship_type、line、
          fare_usd 等資訊。

    範例使用情境：
        使用者問：「從 MS01 到 NR05 最便宜怎麼走？」
        使用者問:「What is the cheapest route from Central Square to Stonehaven?」
        使用者問:「NR01 到 NR05 first class 最低費用路線是哪一條？」
    """
    rel_pattern = _relationship_pattern(network, origin_id, destination_id)
    fare_class = (fare_class or "standard").lower()

    if fare_class == "first":
        fare_expr = "coalesce(r.fare_usd, r.fare_first, r.fare_standard, 0)"
        leg_fare_expr = """
        coalesce(
            relationships(path)[i].fare_usd,
            relationships(path)[i].fare_first,
            relationships(path)[i].fare_standard,
            0
        )
        """
    else:
        fare_expr = "coalesce(r.fare_usd, r.fare_standard, 0)"
        leg_fare_expr = """
        coalesce(
            relationships(path)[i].fare_usd,
            relationships(path)[i].fare_standard,
            0
        )
        """

    cypher = f"""
    MATCH path = (a {{station_id: $origin_id}})-[:{rel_pattern}*1..8]-(b {{station_id: $destination_id}})
    WHERE all(i IN range(0, size(nodes(path)) - 2)
              WHERE NOT nodes(path)[i] IN nodes(path)[i + 1..])
    WITH path,
         reduce(total = 0.0, r IN relationships(path) |
             total + {fare_expr}
         ) AS total_fare_usd
    ORDER BY total_fare_usd ASC, length(path) ASC
    LIMIT 1
    RETURN
        total_fare_usd,
        [n IN nodes(path) | {{
            station_id: n.station_id,
            name: n.name,
            labels: labels(n)
        }}] AS stations,
        [i IN range(0, size(relationships(path)) - 1) | {{
            from_id: nodes(path)[i].station_id,
            from_name: nodes(path)[i].name,
            to_id: nodes(path)[i + 1].station_id,
            to_name: nodes(path)[i + 1].name,
            relationship_type: type(relationships(path)[i]),
            line: relationships(path)[i].line,
            fare_usd: {leg_fare_expr}
        }}] AS legs
    """

    with _driver() as driver:
        with driver.session() as session:
            record = session.run(
                cypher,
                origin_id=origin_id,
                destination_id=destination_id,
            ).single()

            if record is None:
                return {
                    "found": False,
                    "origin_id": origin_id,
                    "destination_id": destination_id,
                    "fare_class": fare_class,
                    "total_fare_usd": None,
                    "stations": [],
                    "legs": [],
                }

            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "fare_class": fare_class,
                "total_fare_usd": record["total_fare_usd"],
                "stations": record["stations"],
                "legs": record["legs"],
            }


def query_alternative_routes(
    origin_id: str,
    destination_id: str,
    avoid_station_id: str,
    network: str = "auto",
    max_routes: int = 3,
) :
    """
    查詢避開指定站點的替代路線。

    用途：
        根據 Neo4j graph 找出從起點到終點的可行替代路線，
        並排除任何包含 avoid_station_id 的路徑。
        本函數主要用於封站、延誤、中斷、繞路與替代方案情境。

    適合使用：
        - 使用者詢問 alternative route、替代路線或其他走法。
        - 使用者明確要求避開某一站，例如「不要經過 NR03」。
        - 使用者表示某站關閉、施工、延誤、中斷或 disruption。
        - 使用者問「如果某站不能走，要怎麼從 A 到 B」。
        - 使用者想知道繞開問題站點後，是否仍有可行路線。

    不適合使用：
        - 若使用者只是一般詢問最快路線，且沒有提到避開站點或替代方案，
          請改用 query_shortest_route。
        - 若使用者詢問最便宜路線或最低票價，
          請改用 query_cheapest_route。
        - 若使用者主要想知道 metro 與 national rail 在哪裡轉乘，
          且沒有要求避開任何站，請改用 query_interchange_path。
        - 若使用者只想知道某站延誤會影響哪些附近站點，
          請改用 query_delay_ripple。
        - 若使用者只問某站直接連到哪些站，
          請改用 query_station_connections。

    參數：
        origin_id:
            起點站 ID。
            Metro station ID 以 "MS" 開頭，例如 "MS01"。
            National rail station ID 以 "NR" 開頭，例如 "NR01"。
        destination_id:
            終點站 ID。
            格式同 origin_id,例如 "MS09" 或 "NR05"。
        avoid_station_id:
            必須避開的站點 ID。
            回傳的任何路線中都不應包含這個站點。
            例如 "NR03"、"MS07"。
        network:
            搜尋網路範圍。
            - "metro"：只搜尋 metro network。
            - "rail"：只搜尋 national rail network。
            - "auto"：自動判斷搜尋範圍，必要時允許跨 metro / national rail 轉乘。
        max_routes:
            最多回傳幾條替代路線。
            預設為 3。若可行路線少於此數量,則只回傳找到的路線。

    回傳：
        list[list[dict]]。
        外層 list 代表多條替代路線。
        每一條路線是一個 leg list;每個 leg dict 包含：
        - from_id: 此路段起點站 ID。
        - from_name: 此路段起點站名稱。
        - to_id: 此路段終點站 ID。
        - to_name: 此路段終點站名稱。
        - relationship_type: METRO_LINK、RAIL_LINK 或 INTERCHANGE_TO。
        - line: metro 或 rail line 名稱；轉乘可能為 None。
        - travel_time_min: 此路段預估時間，單位為分鐘。

        若避開指定站點後沒有任何可行路線，回傳空 list []。

    範例使用情境：
        使用者問：「如果 NR03 關閉,MS01 到 NR05 還有其他路線嗎？」
        使用者問：「從 MS01 到 NR05 請避開 NR03。」
        使用者問:「Find alternative routes from Central Square to Stonehaven avoiding Old Town Junction。」
    """
    rel_pattern = _relationship_pattern(network, origin_id, destination_id)
    max_routes = max(1, int(max_routes))

    cypher = f"""
    MATCH path = (a {{station_id: $origin_id}})-[:{rel_pattern}*1..8]-(b {{station_id: $destination_id}})
    WHERE NONE(n IN nodes(path) WHERE n.station_id = $avoid_station_id)
      AND all(i IN range(0, size(nodes(path)) - 2)
              WHERE NOT nodes(path)[i] IN nodes(path)[i + 1..])
    WITH path,
         [n IN nodes(path) | n.station_id] AS route_key,
         reduce(total = 0, r IN relationships(path) |
             total + coalesce(r.travel_time_min, r.walk_time_min, 0)
         ) AS total_time_min
    ORDER BY total_time_min ASC, length(path) ASC
    WITH route_key, collect({{path: path, total_time_min: total_time_min}})[0] AS best_path
    WITH best_path.path AS path, best_path.total_time_min AS total_time_min
    ORDER BY total_time_min ASC, length(path) ASC
    LIMIT $max_routes
    RETURN
        [i IN range(0, size(relationships(path)) - 1) | {{
            from_id: nodes(path)[i].station_id,
            from_name: nodes(path)[i].name,
            to_id: nodes(path)[i + 1].station_id,
            to_name: nodes(path)[i + 1].name,
            relationship_type: type(relationships(path)[i]),
            line: relationships(path)[i].line,
            travel_time_min: coalesce(
                relationships(path)[i].travel_time_min,
                relationships(path)[i].walk_time_min,
                0
            )
        }}] AS legs
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                cypher,
                origin_id=origin_id,
                destination_id=destination_id,
                avoid_station_id=avoid_station_id,
                max_routes=max_routes,
            )
            return [record["legs"] for record in result]


def query_interchange_path(origin_id: str, destination_id: str) :
    """
    查詢包含 metro 與 national rail 轉乘的跨網路路線。

    用途：
        找出從起點到終點的路線，且路線中必須包含至少一段 INTERCHANGE_TO。
        本函數主要用於解釋 metro 與 national rail 之間如何轉乘、
        在哪一站換乘，以及轉乘步行時間。

    適合使用：
        - 使用者詢問 metro 和 national rail 之間如何轉乘。
        - 使用者明確提到 interchange、transfer、轉乘、換乘或跨網路。
        - 使用者想知道從 metro station 到 national rail station 怎麼走。
        - 使用者想知道從 national rail station 到 metro station 怎麼走。
        - 使用者問「在哪裡從地鐵換到國鐵」或「哪一站可以轉乘」。

    不適合使用：
        - 若使用者只是一般詢問最快路線，且沒有明確要求轉乘說明，
          請改用 query_shortest_route。
        - 若使用者詢問最便宜路線或最低票價，
          請改用 query_cheapest_route。
        - 若使用者詢問避開某站、封站、延誤繞路或替代路線，
          請改用 query_alternative_routes。
        - 若使用者詢問某站延誤會影響哪些附近站點，
          請改用 query_delay_ripple。
        - 若使用者只問某站直接連到哪些站，
          請改用 query_station_connections。
        - 若起點和終點都在同一個網路內，且使用者沒有要求轉乘或 interchange,
          不應優先使用本函數。

    參數：
        origin_id:
            起點站 ID。
            Metro station ID 以 "MS" 開頭，例如 "MS01"。
            National rail station ID 以 "NR" 開頭，例如 "NR01"。
        destination_id:
            終點站 ID。
            格式同 origin_id,例如 "MS09" 或 "NR05"。

    回傳：
        dict,包含:
        - found: 是否找到包含轉乘的跨網路路線。
        - origin_id: 起點站 ID。
        - destination_id: 終點站 ID。
        - stations: 依序排列的站點清單。
        - interchange_points: 轉乘路段清單，包含 from_id、to_id、from_name、
          to_name 與 walk_time_min。
        - total_time_min: 預估總旅行時間，包含搭乘時間與轉乘步行時間。

        若找不到包含 INTERCHANGE_TO 的路線,found 會是 False。

    範例使用情境：
        使用者問:「MS01 到 NR05 要在哪裡轉乘？」
        使用者問:「How do I transfer from metro to national rail from Central Square?」
        使用者問：「從 NR01 到 MS18 的跨網路轉乘路線是什麼？」
    """
    cypher = """
    MATCH path = (a {station_id: $origin_id})-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..8]-(b {station_id: $destination_id})
    WHERE ANY(r IN relationships(path) WHERE type(r) = "INTERCHANGE_TO")
      AND all(i IN range(0, size(nodes(path)) - 2)
              WHERE NOT nodes(path)[i] IN nodes(path)[i + 1..])
    WITH path,
         reduce(total = 0, r IN relationships(path) |
             total + coalesce(r.travel_time_min, r.walk_time_min, 0)
         ) AS total_time_min
    ORDER BY total_time_min ASC, length(path) ASC
    LIMIT 1
    RETURN
        total_time_min,
        [n IN nodes(path) | {
            station_id: n.station_id,
            name: n.name,
            labels: labels(n)
        }] AS stations,
        [n IN nodes(path)
            WHERE "MetroStation" IN labels(n) OR "NationalRailStation" IN labels(n)
            | {
                station_id: n.station_id,
                name: n.name,
                labels: labels(n)
            }
        ] AS all_points,
        [i IN range(0, size(relationships(path)) - 1)
            WHERE type(relationships(path)[i]) = "INTERCHANGE_TO"
            | {
                from_id: nodes(path)[i].station_id,
                from_name: nodes(path)[i].name,
                to_id: nodes(path)[i + 1].station_id,
                to_name: nodes(path)[i + 1].name,
                walk_time_min: coalesce(relationships(path)[i].walk_time_min, 0)
            }
        ] AS interchange_points
    """

    with _driver() as driver:
        with driver.session() as session:
            record = session.run(
                cypher,
                origin_id=origin_id,
                destination_id=destination_id,
            ).single()

            if record is None:
                return {
                    "found": False,
                    "origin_id": origin_id,
                    "dest[r IN relationships(path) WHERE r.line IS NOT NULL | r.line] AS linesination_id": destination_id,
                    "stations": [],
                    "interchange_points": [],
                    "total_time_min": None,
                }

            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "stations": record["stations"],
                "interchange_points": record["interchange_points"],
                "total_time_min": record["total_time_min"],
            }


def query_delay_ripple(delayed_station_id: str, hops: int = 2) :
    """
        查詢某一站延誤或中斷時，可能受影響的附近站點。

        用途：
            從指定的 delayed_station_id 出發，在 Neo4j graph 中向外搜尋 N hops，
            找出可能受到延誤、封閉、中斷或營運異常影響的站點。
            本函數用於路網影響範圍分析，不是用來規劃 A 到 B 的路線。

        適合使用：
            - 使用者詢問某站延誤會影響哪些站。
            - 使用者詢問 disruption impact、delay ripple、ripple effect 或 affected stations。
            - 使用者詢問某站 N stops / N hops 內有哪些站可能受影響。
            - 使用者想知道某個 station incident 的擴散範圍。
            - 使用者問「如果 NR03 出問題，附近哪些站會受影響」。

        不適合使用：
            - 若使用者詢問從 A 到 B 怎麼走，請改用 query_shortest_route。
            - 若使用者詢問從 A 到 B 最便宜怎麼走，請改用 query_cheapest_route。
            - 若使用者詢問避開某站後是否有替代路線，
            請改用 query_alternative_routes。
            - 若使用者詢問 metro 與 national rail 的轉乘路徑，
            請改用 query_interchange_path。
            - 若使用者只想知道某站直接連到哪些站，
            請改用 query_station_connections。

        參數：
            delayed_station_id:
                發生延誤、中斷或異常的起始站點 ID。
                Metro station ID 以 "MS" 開頭，例如 "MS01"。
                National rail station ID 以 "NR" 開頭，例如 "NR03"。
            hops:
                從 delayed_station_id 向外搜尋的 graph hop 數。
                預設為 2。
                數值越大，代表搜尋越遠的影響範圍。
                本系統會限制 hops 在合理範圍內，避免查詢過大。

        回傳:
            list[dict]，每個 dict 代表一個可能受影響站點，包含：
            - station_id: 受影響站點 ID。
            - name: 受影響站點名稱。
            - labels: Neo4j labels,例如 MetroStation 或 NationalRailStation。
            - hops_away: 從延誤站點到該站點的最短 graph hop 數。
            - lines_affected: 影響路徑中涉及的 metro line、rail line 或 INTERCHANGE。

            若找不到任何受影響站點，回傳空 list []。

        範例使用情境：
            使用者問:「NR03 延誤會影響哪些站？」
            使用者問:「Show affected stations within 2 hops of Old Town Junction。」
            使用者問:「如果 MS01 出問題，附近兩站內會被波及嗎？」
        """
    hops = max(1, min(int(hops), 10))

    cypher = f"""
    MATCH path = (s {{station_id: $delayed_station_id}})-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..{hops}]-(affected)
    WHERE s <> affected
    WITH affected,
         length(path) AS hops_away,
    
    [r IN relationships(path) |
      CASE
        WHEN r.line IS NOT NULL THEN r.line
        WHEN type(r) = "INTERCHANGE_TO" THEN "INTERCHANGE"
        ELSE null
      END
    ] AS lines
         
    ORDER BY hops_away ASC, affected.station_id ASC
    RETURN
        affected.station_id AS station_id,
        affected.name AS name,
        labels(affected) AS labels,
        min(hops_away) AS hops_away,
        collect(lines) AS line_lists
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(cypher, delayed_station_id=delayed_station_id)

            rows = []
            for record in result:
                lines_affected = sorted({
                    line
                    for line_list in record["line_lists"]
                    for line in line_list
                    if line is not None
                })

                rows.append({
                    "station_id": record["station_id"],
                    "name": record["name"],
                    "labels": record["labels"],
                    "hops_away": record["hops_away"],
                    "lines_affected": lines_affected,
                })

            return rows
