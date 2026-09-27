from t2sql.db.introspect import introspect, quote_ident
from t2sql.retrieval.value_index import ValueIndex


def test_introspection_finds_tables_keys_and_examples(demo_db):
    schema = introspect(demo_db)
    assert len(schema.tables) == 10
    fk_pairs = {(fk.table, fk.ref_table) for fk in schema.foreign_keys}
    assert ("sections", "classrooms") in fk_pairs
    assert ("enrollments", "students") in fk_pairs
    text = schema.render()
    assert "# Table: departments" in text and "Computer Science" in text
    assert "【Foreign keys】" in text


def test_render_subset_keeps_join_keys(demo_db):
    schema = introspect(demo_db)
    text = schema.render(keep={"courses": {"course_name"}, "departments": {"dept_name"}})
    assert "# Table: students" not in text
    assert "dept_id" in text  # FK column kept even though not requested


def test_quote_ident():
    assert quote_ident("dept_name") == "dept_name"
    assert quote_ident("County Name") == "`County Name`"


def test_value_index_maps_question_words_to_stored_values(demo_db):
    idx = ValueIndex.build(demo_db)
    hits = [
        (m.table, m.column, m.value)
        for m in idx.search("How many students take courses in the computer science department?")
    ]
    assert ("departments", "dept_name", "Computer Science") in hits


def test_value_index_ignores_unrelated_questions(demo_db):
    idx = ValueIndex.build(demo_db)
    assert idx.search("How many rows are there?") == []


def test_quantities_are_not_matched_to_stored_values(tmp_path):
    import sqlite3

    db = tmp_path / "s.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE frpm (county TEXT, low_grade TEXT);"
        "INSERT INTO frpm VALUES ('Los Angeles', '5'), ('Kern', 'K'), ('Alameda', '12');"
    )
    conn.commit()
    conn.close()
    idx = ValueIndex.build(db)
    hits = [m.value for m in idx.search("Which 5 counties have the most schools? Alameda first")]
    assert "5" not in hits and "Alameda" in hits
