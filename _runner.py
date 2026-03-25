import subprocess, sys, os

os.chdir(r'c:\Users\Usuario\agent-skills')

# First test: does it import?
r1 = subprocess.run(
    [sys.executable, '-c', 'from runtime.step_control import check_condition; print("import ok")'],
    capture_output=True, text=True
)

# Second test: run actual tests
r2 = subprocess.run(
    [sys.executable, '-m', 'runtime.test_step_control_flow'],
    capture_output=True, text=True,
    timeout=120
)

out = []
out.append(f"=== Import check ===")
out.append(f"stdout: {r1.stdout}")
out.append(f"stderr: {r1.stderr}")
out.append(f"rc: {r1.returncode}")
out.append(f"=== Test run ===")
out.append(f"stdout: {r2.stdout}")
out.append(f"stderr: {r2.stderr}")
out.append(f"rc: {r2.returncode}")

with open(r'c:\Users\Usuario\agent-skills\test_output_cf.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
print("done")
