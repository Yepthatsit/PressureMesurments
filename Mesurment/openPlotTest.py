import subprocess
from time import  sleep
FileName = "C:/Users/karol/Desktop/Praca_AGH/PressureMesurments/UtilityFiles/Stabilization.json"
process = subprocess.Popen(f"py ../Ploting/JsonPlotter.py {FileName}")
#sleep(100)
#process.terminate()