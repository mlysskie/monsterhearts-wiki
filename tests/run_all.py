"""Corre todas las pruebas, cada una con una base nueva.

    python tests/run_all.py                 # con SQLite temporal
    DATABASE_URL=postgresql://... python tests/run_all.py   # contra un Postgres VACÍO de prueba

Ojo: con DATABASE_URL las pruebas escriben datos; nunca la apuntes a la base de Railway.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = ["test_wiki.py", "test_pueblonet.py", "test_passwords.py"]

failed = 0
for name in TESTS:
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, MASTER_PASSWORD="secreto", INITIAL_ACCESS_CODE="luna-1996",
                   SQLITE_PATH=os.path.join(tmp, "test.db"))
        r = subprocess.run([sys.executable, "-W", "ignore", os.path.join(HERE, name)], env=env,
                           capture_output=True, text=True, cwd=tmp)
        last = (r.stdout.strip().splitlines() or [""])[-1]
        print(f"{'ok  ' if r.returncode == 0 else 'FALLA'} {name}: {last}")
        if r.returncode:
            failed += 1
            print(r.stderr[-2000:])
sys.exit(1 if failed else 0)
