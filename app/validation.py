import sqlglot

def validate_sql(sql: str) -> tuple[bool, str, str, str]:
    """Validates the generated SQL structure and syntax."""
    sql = sql.strip()
    
    # Quick sanity check before parsing
    forbidden_keywords = ['DROP', 'DELETE', 'INSERT', 'UPDATE', 'ALTER', 'CREATE']
    upper_sql = sql.upper()
    for kw in forbidden_keywords:
        if kw in upper_sql:
            return False, f"Forbidden keyword detected: {kw}", sql, "INVALID"
            
    try:
        # Parse into AST
        parsed = sqlglot.parse_one(sql)
        
        # Check statement type
        if not isinstance(parsed, sqlglot.exp.Select):
            return False, "Only SELECT statements are allowed.", sql, type(parsed).__name__
            
        # Schema-Aware Column Validation
        from app.database import TABLES_DDL
        valid_columns = {'*'}
        for ddl in TABLES_DDL.values():
            for line in ddl.split('\n'):
                line = line.strip()
                if not line or line.startswith('CREATE') or line.startswith('PRIMARY') or line.startswith(')'):
                    continue
                parts = line.split()
                if parts:
                    valid_columns.add(parts[0].lower().strip(','))
        
        # Collect SELECT-level aliases (e.g., COUNT(*) AS course_count)
        # These are valid references in ORDER BY / HAVING clauses
        select_aliases = set()
        for alias_node in parsed.find_all(sqlglot.exp.Alias):
            select_aliases.add(alias_node.alias.lower())
                    
        for col in parsed.find_all(sqlglot.exp.Column):
            col_name = col.name.lower()
            if col_name not in valid_columns and col_name not in select_aliases:
                return False, f"Hallucinated column detected: {col.name}", sql, "INVALID"

        # Format output: uppercase keywords, normalized
        normalized_sql = parsed.sql(dialect="sqlite")
        return True, "", normalized_sql, "SELECT"
        
    except sqlglot.errors.ParseError as e:
        return False, f"Syntax Error: {str(e)}", sql, "INVALID"
    except Exception as e:
        return False, f"Validation Error: {str(e)}", sql, "INVALID"