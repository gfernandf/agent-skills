import subprocess, sys, os
os.chdir(r'c:\Users\Usuario\agent-skills')
r = subprocess.run([sys.executable, '-m', 'runtime.test_step_control_flow'], capture_output=True, text=True)
with open('_test_out.txt', 'w') as f:
    f.write(f"STDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}\nRC: {r.returncode}\n")
