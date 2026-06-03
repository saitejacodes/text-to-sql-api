from sentence_transformers import SentenceTransformer
import numpy as np
from app.models import RetrieveDetails
from typing import Optional

class Retriever:
    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)

            # Rich schema metadata: description + columns + keywords for semantic search
            cls._instance.schemas = {
                "departments": {
                    "description": "departments table: stores academic department info such as Computer Science, Mathematics, Physics, Chemistry, Biology. Columns: dept_id (PK), dept_name",
                    "columns": "dept_id INTEGER PRIMARY KEY, dept_name TEXT",
                    "keywords": ["department", "dept", "faculty", "division", "school", "subject", "major"],
                },
                "courses": {
                    "description": "courses table: stores course or class information including subject name, credits, and whether the course is online or in-person. Columns: course_id, course_name, dept_id, credits, is_online",
                    "columns": "course_id INTEGER PRIMARY KEY, course_name TEXT, dept_id INTEGER, credits INTEGER, is_online BOOLEAN",
                    "keywords": ["course", "class", "subject", "online", "credit", "curriculum", "lecture", "module"],
                },
                "students": {
                    "description": "students table: stores student records including name and the year they enrolled. Columns: student_id, first_name, last_name, enrollment_year",
                    "columns": "student_id INTEGER PRIMARY KEY, first_name TEXT, last_name TEXT, enrollment_year INTEGER",
                    "keywords": ["student", "learner", "undergraduate", "pupil", "person", "who enrolled", "year"],
                },
                "enrollments": {
                    "description": "enrollments table: records which students are registered in which courses, along with their semester and grade. Columns: enrollment_id, student_id, course_id, semester, grade",
                    "columns": "enrollment_id INTEGER PRIMARY KEY, student_id INTEGER, course_id INTEGER, semester TEXT, grade TEXT",
                    "keywords": ["enrollment", "enroll", "register", "registration", "grade", "semester", "count students", "taking"],
                },
                "instructors": {
                    "description": "instructors table: stores faculty members including professors and teachers and the department they belong to. Columns: instructor_id, first_name, last_name, dept_id",
                    "columns": "instructor_id INTEGER PRIMARY KEY, first_name TEXT, last_name TEXT, dept_id INTEGER",
                    "keywords": ["instructor", "professor", "teacher", "faculty", "staff", "lecturer", "teaches", "dr"],
                },
                "classrooms": {
                    "description": "classrooms table: physical rooms and buildings with their seating capacity. Includes Stata Center, Building 10, Main Hall. Columns: classroom_id, building, room_number, capacity",
                    "columns": "classroom_id INTEGER PRIMARY KEY, building TEXT, room_number TEXT, capacity INTEGER",
                    "keywords": ["classroom", "room", "building", "capacity", "seats", "location", "venue", "stata", "hall"],
                },
                "time_slots": {
                    "description": "time_slots table: class schedule time periods specifying day of week and start/end times. E.g. MWF 10-11am, TR 1-2:30pm. Columns: time_slot_id, day_of_week, start_time, end_time",
                    "columns": "time_slot_id INTEGER PRIMARY KEY, day_of_week TEXT, start_time TEXT, end_time TEXT",
                    "keywords": ["time", "schedule", "slot", "day", "morning", "afternoon", "monday", "mwf", "hours", "when", "period"],
                },
                "sections": {
                    "description": "sections table: specific offerings of a course linking course, instructor, classroom, and time slot for a given semester. Columns: section_id, course_id, instructor_id, classroom_id, time_slot_id, semester",
                    "columns": "section_id INTEGER PRIMARY KEY, course_id INTEGER, instructor_id INTEGER, classroom_id INTEGER, time_slot_id INTEGER, semester TEXT",
                    "keywords": ["section", "offering", "instance", "taught", "offered", "semester", "teaches"],
                },
                "prerequisites": {
                    "description": "prerequisites table: defines course dependency chains — which courses must be completed before another can be taken. Columns: course_id, prereq_id",
                    "columns": "course_id INTEGER, prereq_id INTEGER",
                    "keywords": ["prerequisite", "prereq", "requirement", "before", "must take", "depends on", "required", "prior"],
                },
                "advisors": {
                    "description": "advisors table: links students to their assigned faculty advisor or academic mentor. Columns: student_id, instructor_id",
                    "columns": "student_id INTEGER, instructor_id INTEGER",
                    "keywords": ["advisor", "adviser", "mentor", "advise", "guidance", "counselor", "assigned to"],
                },
            }

            cls._instance.gold_queries = [
                {"q": "Which departments have more than 2 courses?", "sql": "SELECT d.dept_name, COUNT(c.course_id) AS course_count FROM departments d JOIN courses c ON d.dept_id = c.dept_id GROUP BY d.dept_name HAVING COUNT(c.course_id) > 2"},
                {"q": "List all online courses.", "sql": "SELECT course_name, credits FROM courses WHERE is_online = 1"},
                {"q": "Which students are advised by Dr. Alan Turing?", "sql": "SELECT s.first_name, s.last_name FROM students s JOIN advisors a ON s.student_id = a.student_id JOIN instructors i ON a.instructor_id = i.instructor_id WHERE i.first_name = 'Dr. Alan' AND i.last_name = 'Turing'"},
                {"q": "Which students are not enrolled in any course?", "sql": "SELECT first_name, last_name FROM students WHERE student_id NOT IN (SELECT DISTINCT student_id FROM enrollments)"},
                {"q": "Rank departments by number of courses in descending order.", "sql": "SELECT d.dept_name, COUNT(c.course_id) AS course_count FROM departments d JOIN courses c ON d.dept_id = c.dept_id GROUP BY d.dept_name ORDER BY course_count DESC"},
                {"q": "How many students enrolled in 2023?", "sql": "SELECT COUNT(*) FROM students WHERE enrollment_year = 2023"},
                {"q": "What is the total capacity of classrooms in the Stata Center?", "sql": "SELECT SUM(capacity) FROM classrooms WHERE building = 'Stata Center'"},
                {"q": "List the prerequisites for Algorithms.", "sql": "SELECT c2.course_name FROM courses c1 JOIN prerequisites p ON c1.course_id = p.course_id JOIN courses c2 ON p.prereq_id = c2.course_id WHERE c1.course_name = 'Algorithms'"},
                {"q": "Who is teaching Intro to CS?", "sql": "SELECT i.first_name, i.last_name FROM instructors i JOIN sections s ON i.instructor_id = s.instructor_id JOIN courses c ON s.course_id = c.course_id WHERE c.course_name = 'Intro to CS'"},
                {"q": "Find students who got an A in Calculus I.", "sql": "SELECT s.first_name, s.last_name FROM students s JOIN enrollments e ON s.student_id = e.student_id JOIN courses c ON e.course_id = c.course_id WHERE c.course_name = 'Calculus I' AND e.grade = 'A'"},
            ]

            cls._instance.table_names = list(cls._instance.schemas.keys())
            cls._instance.embeddings = None
            cls._instance.few_shot_embeddings = None
        return cls._instance

    def load_model(self):
        if self._model is None:
            self._model = SentenceTransformer("BAAI/bge-large-en-v1.5")
            texts = [self.schemas[n]["description"] for n in self.table_names]
            self.embeddings = self._model.encode(texts, normalize_embeddings=True)
            
            gold_texts = ["Represent this sentence for searching relevant passages: " + g["q"] for g in self.gold_queries]
            self.few_shot_embeddings = self._model.encode(gold_texts, normalize_embeddings=True)

    def retrieve_few_shot(self, question: str, top_k: int = 3) -> str:
        if self._model is None:
            self.load_model()
            
        bge_instruction = "Represent this sentence for searching relevant passages: "
        q_emb = self._model.encode([bge_instruction + question], normalize_embeddings=True)[0]
        
        sims = [float(np.dot(q_emb, emb)) for emb in self.few_shot_embeddings]
        top_idx = np.argsort(sims)[-top_k:][::-1]
        
        examples = []
        for i, idx in enumerate(top_idx):
            examples.append(f"-- Example {i+1}\nQuestion: {self.gold_queries[idx]['q']}\nSQL: {self.gold_queries[idx]['sql']}")
            
        return "\n\n".join(examples)

    def get_schema_for_tables(self, tables: list) -> dict:
        """Returns schema descriptions (description + columns) for the specified tables."""
        return {t: self.schemas[t] for t in tables if t in self.schemas}

    def retrieve_tables(
        self, question: str, top_k: int = 3
    ) -> tuple[list[str], list[float], float, dict]:
        if self._model is None:
            self.load_model()

        # BGE models need an instruction prefix on queries for optimal retrieval
        bge_instruction = "Represent this sentence for searching relevant passages: "
        q_emb = self._model.encode([bge_instruction + question], normalize_embeddings=True)[0]

        # Cosine similarity (pre-normalized → simple dot product)
        sims = [float(np.dot(q_emb, emb)) for emb in self.embeddings]

        # Sparse/Keyword Boost (Hybrid Retrieval)
        import re
        q_lower = question.lower()
        hybrid_scores = []
        for i, table in enumerate(self.table_names):
            dense_score = sims[i]
            keywords = self.schemas[table]["keywords"]
            # Word boundary regex to ensure exact keyword match (e.g., "course" doesn't match "courses" unless specified)
            # Actually, we want plural tolerance, so simple `k in q_lower` is often better for simple keywords
            # But let's use a smart boundary that allows plurals:
            keyword_match = any(re.search(rf'\b{re.escape(k)}s?\b', q_lower) for k in keywords)
            
            # Boost score by 0.25 if exact keyword match is found
            hybrid_score = dense_score + (0.25 if keyword_match else 0.0)
            hybrid_scores.append(hybrid_score)

        top_idx = np.argsort(hybrid_scores)[-top_k:][::-1]
        retrieved = [self.table_names[i] for i in top_idx]
        scores    = [round(hybrid_scores[i], 4) for i in top_idx]
        confidence = round(sum(scores) / len(scores), 4) if scores else 0.0

        details = {}
        q_lower = question.lower()
        for table, score in zip(retrieved, scores):
            meta = self.schemas[table]
            kw = next((k for k in meta["keywords"] if k in q_lower), table)
            details[table] = RetrieveDetails(
                relevance_score=score,
                reason=f"Matched on '{kw}' — {meta['description'].split('.')[0]}.",
            )

        return retrieved, scores, confidence, details


retriever = Retriever()