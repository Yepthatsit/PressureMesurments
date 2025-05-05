from pyqtgraph.examples.hdf5 import fileName
from typing_extensions import Required
from pymeasure.instruments.lakeshore import lakeshore331, LakeShore331
from pymeasure.instruments.srs import  sr860
from Stabilization import Stabilisation_atomic_json
from time import  sleep
import  subprocess
import os
class PressureMesurment:
    def __init__(self,LakeshoreAdress:Required[str], LockInAdress:Required[str]):
        """
        :param LakeshoreAdress:
        :param LockInAdress:
        """
        self.Lakeshore = LakeShore331(LakeshoreAdress)
        self.LockIn = sr860(LockInAdress)

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        :param exc_type:
        :param exc_val:
        :param exc_tb:
        :return:
        """
        self.Lakeshore.close()
        self.LockIn.close()

    def GoToTemperature(self, FileName:Required[str], TargetTemp:Required[float], Ramp:float = 4, SampleTemperatureTolerance:float = 0.5 , ControlTemperatureTolerance:float = 0.5, MeasurmentDelay:float = 5) -> None:
        """
        :param FileName:
        :param TargetTemp:
        :param Ramp:
        :param SampleTemperatureTolerance:
        :param ControlTemperatureTolerance:
        :return:
        """
        fileDir = os.path.dirname(FileName)
        mesurmentNumber = 1
        if(not os.path.exists(fileDir)):
            print(f"Creating directory: {fileDir}")
            os.mkdir(fileDir)
        if(not os.path.exists(FileName)):
            file = open(FileName,"w")
            file.write("T_A[K] T_B[K] Setpoint[K] sr860x[V] sr860y[V] sr860f[Hz] sr860sin[V] sr860tht[deg] sr860phs[deg] sr860mgn[V] HTR CNT yyyy-mm-dd hh:mm:ss.ccccc")
            file.close()
        TempControl = self.Lakeshore.input_B.temperature
        TempSample = self.Lakeshore.input_A.temperature
        self.Lakeshore.write(f"RAMP 1,1,{Ramp}")
        self.Lakeshore.write(f"SETP 1,{TargetTemp}")
        process = subprocess.Popen(f"python /Ploting/UniversalPlotter.py {fileName} T_A[K],sr860x[V]")

        while(abs(TempControl - TargetTemp) > ControlTemperatureTolerance or abs(TempSample - TargetTemp) > SampleTemperatureTolerance ):
            TempSample = self.Lakeshore.input_B.temperature
            TempControl = self.Lakeshore.input_B.temperature

            sleep(MeasurmentDelay)

        process.terminate()