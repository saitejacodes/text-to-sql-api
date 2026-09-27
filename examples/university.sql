-- Demo database: a small university registrar (10 tables).
CREATE TABLE departments (
            dept_id   INTEGER PRIMARY KEY,
            dept_name TEXT NOT NULL
        );
CREATE TABLE courses (
            course_id   INTEGER PRIMARY KEY,
            course_name TEXT NOT NULL,
            dept_id     INTEGER,
            credits     INTEGER,
            is_online   BOOLEAN,
            FOREIGN KEY (dept_id) REFERENCES departments(dept_id)
        );
CREATE TABLE students (
            student_id      INTEGER PRIMARY KEY,
            first_name      TEXT,
            last_name       TEXT,
            enrollment_year INTEGER
        );
CREATE TABLE enrollments (
            enrollment_id INTEGER PRIMARY KEY,
            student_id    INTEGER,
            course_id     INTEGER,
            semester      TEXT,
            grade         TEXT,
            FOREIGN KEY (student_id) REFERENCES students(student_id),
            FOREIGN KEY (course_id) REFERENCES courses(course_id)
        );
CREATE TABLE instructors (
            instructor_id INTEGER PRIMARY KEY,
            first_name    TEXT,
            last_name     TEXT,
            dept_id       INTEGER,
            FOREIGN KEY (dept_id) REFERENCES departments(dept_id)
        );
CREATE TABLE classrooms (
            classroom_id INTEGER PRIMARY KEY,
            building     TEXT,
            room_number  TEXT,
            capacity     INTEGER
        );
CREATE TABLE time_slots (
            time_slot_id INTEGER PRIMARY KEY,
            day_of_week  TEXT,
            start_time   TEXT,
            end_time     TEXT
        );
CREATE TABLE sections (
            section_id    INTEGER PRIMARY KEY,
            course_id     INTEGER,
            instructor_id INTEGER,
            classroom_id  INTEGER,
            time_slot_id  INTEGER,
            semester      TEXT,
            FOREIGN KEY (course_id) REFERENCES courses(course_id),
            FOREIGN KEY (instructor_id) REFERENCES instructors(instructor_id),
            FOREIGN KEY (classroom_id) REFERENCES classrooms(classroom_id),
            FOREIGN KEY (time_slot_id) REFERENCES time_slots(time_slot_id)
        );
CREATE TABLE prerequisites (
            course_id INTEGER,
            prereq_id INTEGER,
            PRIMARY KEY (course_id, prereq_id),
            FOREIGN KEY (course_id) REFERENCES courses(course_id),
            FOREIGN KEY (prereq_id) REFERENCES courses(course_id)
        );
CREATE TABLE advisors (
            student_id    INTEGER,
            instructor_id INTEGER,
            PRIMARY KEY (student_id, instructor_id),
            FOREIGN KEY (student_id) REFERENCES students(student_id),
            FOREIGN KEY (instructor_id) REFERENCES instructors(instructor_id)
        );

-- Departments
INSERT INTO departments (dept_id, dept_name) VALUES
  (1,'Computer Science'),(2,'Mathematics'),(3,'Physics'),
  (4,'Chemistry'),(5,'Biology');

-- Courses
INSERT INTO courses (course_id, course_name, dept_id, credits, is_online) VALUES
  (101,'Intro to CS',         1, 4, 0),
  (102,'Data Structures',     1, 4, 0),
  (103,'Algorithms',          1, 4, 0),
  (104,'Online ML',           1, 3, 1),
  (201,'Calculus I',          2, 4, 0),
  (202,'Linear Algebra',      2, 4, 0),
  (203,'Statistics Online',   2, 3, 1),
  (301,'Physics I',           3, 4, 0),
  (302,'Quantum Mechanics',   3, 4, 0),
  (401,'Organic Chemistry',   4, 4, 0),
  (402,'Biochemistry Online', 4, 3, 1),
  (501,'Cell Biology',        5, 4, 0);

-- Students
INSERT INTO students (student_id, first_name, last_name, enrollment_year) VALUES
  (1,'Alice',   'Smith',   2023),
  (2,'Bob',     'Jones',   2022),
  (3,'Charlie', 'Brown',   2023),
  (4,'Diana',   'Prince',  2021),
  (5,'Eve',     'Wilson',  2022),
  (6,'Frank',   'Miller',  2023),
  (7,'Grace',   'Lee',     2021),
  (8,'Henry',   'Davis',   2022),
  (9,'Iris',    'Chen',    2023),
  (10,'Jack',   'Taylor',  2021);

-- Enrollments
INSERT INTO enrollments (enrollment_id, student_id, course_id, semester, grade) VALUES
  (1, 1, 101,'Fall 2023',   'A'),
  (2, 2, 102,'Spring 2024', 'B'),
  (3, 1, 104,'Fall 2023',   'A'),
  (4, 3, 101,'Fall 2023',   'B'),
  (5, 4, 202,'Fall 2021',   'A'),
  (6, 5, 201,'Fall 2022',   'C'),
  (7, 6, 301,'Fall 2023',   'B'),
  (8, 7, 501,'Spring 2022', 'A'),
  (9, 8, 102,'Fall 2022',   'B'),
  (10,9, 103,'Fall 2023',   'A'),
  (11,10,401,'Spring 2021', 'C'),
  (12,1, 201,'Spring 2024', 'A'),
  (13,2, 203,'Fall 2022',   'B'),
  (14,3, 104,'Fall 2023',   'A'),
  (15,4, 101,'Fall 2021',   'A');

-- Instructors
INSERT INTO instructors (instructor_id, first_name, last_name, dept_id) VALUES
  (1,'Dr. Alan',    'Turing',    1),
  (2,'Dr. Ada',     'Lovelace',  2),
  (3,'Dr. Richard', 'Feynman',   3),
  (4,'Dr. Marie',   'Curie',     4),
  (5,'Dr. Charles', 'Darwin',    5),
  (6,'Dr. Linus',   'Torvalds',  1);

-- Classrooms
INSERT INTO classrooms (classroom_id, building, room_number, capacity) VALUES
  (1,'Stata Center', '32-123',  100),
  (2,'Building 10',  '10-250',  300),
  (3,'Main Hall',    'MH-100',  500),
  (4,'Science Wing', 'SW-201',  150),
  (5,'Tech Tower',   'TT-301',   75);

-- Time slots
INSERT INTO time_slots (time_slot_id, day_of_week, start_time, end_time) VALUES
  (1,'MWF','10:00','11:00'),
  (2,'TR', '13:00','14:30'),
  (3,'MWF','14:00','15:00'),
  (4,'TR', '09:00','10:30'),
  (5,'MW', '16:00','17:30');

-- Sections
INSERT INTO sections (section_id, course_id, instructor_id, classroom_id, time_slot_id, semester) VALUES
  (1, 101, 1, 1, 1,'Fall 2023'),
  (2, 102, 1, 2, 2,'Spring 2024'),
  (3, 201, 2, 3, 3,'Fall 2023'),
  (4, 301, 3, 4, 4,'Fall 2023'),
  (5, 401, 4, 5, 5,'Fall 2023'),
  (6, 501, 5, 4, 2,'Spring 2022'),
  (7, 103, 6, 1, 3,'Fall 2023');

-- Prerequisites
INSERT INTO prerequisites (course_id, prereq_id) VALUES
  (102,101),
  (103,102),
  (302,301),
  (202,201);

-- Advisors
INSERT INTO advisors (student_id, instructor_id) VALUES
  (1,1),(2,2),(3,1),(4,2),(5,3),
  (6,3),(7,5),(8,1),(9,6),(10,4);
