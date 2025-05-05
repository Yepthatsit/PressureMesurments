import subprocess
from time import  sleep
FileName = "C:/Users/karol/Desktop/Praca_AGH/PressureMesurments/test.csv"
process = subprocess.Popen(f"py ../Ploting/UniversalPlotter.py {FileName} T_A[K],SR860x[V]")
sleep(10)
process.terminate()