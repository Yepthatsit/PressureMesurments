import subprocess
from time import  sleep
FileName = "D:/OneDrive/_SupMagMat_Uniaxial_Pressure/Software_py/PressureMesurments-master/Mesurment/freecooldown.dat"
process = subprocess.Popen(f"py ../Ploting/UniversalPlotter.py {FileName} T_A[K],SR860x[V]")
sleep(100)
process.terminate()