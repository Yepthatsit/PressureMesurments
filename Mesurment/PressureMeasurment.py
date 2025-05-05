import numpy as np
from pyqtgraph.examples.hdf5 import fileName
from typing_extensions import Required
from pymeasure.instruments.lakeshore import lakeshore331, LakeShore331
from pymeasure.instruments.srs import  SR860
from Stabilization.Stabilisation_atomic_json import  TemperatureStabilizer
from time import  sleep
import datetime
import  subprocess
import os
class PressureMesurment:
    def __init__(self,LakeshoreAdress:Required[str],
                 LockInAdress:Required[str],
                 SlopeTolerance:Required[float],
                 InterceptTolerance:Required[float],
                 NumberOfStabilizationPoint:Required[int],
                 SamplingTime:Required[float]):
        """
        :param LakeshoreAdress:
        :param LockInAdress:
        """
        self.Lakeshore = LakeShore331(LakeshoreAdress)
        self.LockIn = SR860(LockInAdress)
        self.SlopeTolerance = SlopeTolerance
        self.InterceptTolerance = InterceptTolerance
        self.NumOfStabPoints = NumberOfStabilizationPoint
        self.SplTime = SamplingTime

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        :param exc_type:
        :param exc_val:
        :param exc_tb:
        :return:
        """
        #self.Lakeshore.close()
        #self.LockIn.close()
        pass
    def __GetFullParametersList(self,mesurmentNumber ) -> list:
        ParametersMeasured = []
        ParametersMeasured.append(self.Lakeshore.ask("KRDG? A"))
        ParametersMeasured.append(self.Lakeshore.ask("KRDG? B"))
        ParametersMeasured.append(self.Lakeshore.ask("SETP? 1"))
        ParametersMeasured.append(self.LockIn.x)
        ParametersMeasured.append(self.LockIn.y)
        ParametersMeasured.append(self.LockIn.frequency)
        ParametersMeasured.append(self.LockIn.sine_voltage)
        ParametersMeasured.append(self.LockIn.theta)
        ParametersMeasured.append(self.LockIn.phase)
        ParametersMeasured.append(self.LockIn.magnitude)
        ParametersMeasured.append(self.Lakeshore.ask("HTR?"))
        ParametersMeasured.append(mesurmentNumber)
        ParametersMeasured.append(datetime.date)
        ParametersMeasured.append(datetime.time)
        pass
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
            file.write("T_A[K] T_B[K] Setpoint[K] SR860x[V] SR860y[V] SR860f[Hz] SR860sin[V] SR860tht[deg] SR860phs[deg] SR860mgn[V] HTR CNT yyyy-mm-dd hh:mm:ss.ccccc")
            file.close()
        TempControl = self.Lakeshore.input_B.temperature
        TempSample = self.Lakeshore.input_A.temperature
        self.Lakeshore.write(f"RAMP 1,1,{Ramp}")
        self.Lakeshore.write(f"SETP 1,{TargetTemp}")
        process = subprocess.Popen(f"python /Ploting/UniversalPlotter.py {fileName} T_A[K],SR860x[V]")

        while(abs(TempControl - TargetTemp) > ControlTemperatureTolerance or abs(TempSample - TargetTemp) > SampleTemperatureTolerance ):
            TempSample = self.Lakeshore.input_A.temperature
            TempControl = self.Lakeshore.input_B.temperature
            ParametersMeasured = self.__GetFullParametersList(mesurmentNumber)
            file = open(fileName,'a')
            file.write(" ".join(ParametersMeasured) + "\n")
            file.close()
            sleep(MeasurmentDelay)
        process.terminate()

    def StabilizationMesurment(self,FileName:Required[str], StartTemp:Required[float], EndTemp:Required[float], NumberOfPoints:Required[int]):
        temperatures = list(np.linspace(StartTemp,EndTemp,NumberOfPoints))
        temperatures = temperatures + temperatures[1::-1]
        fileDir = os.path.dirname(FileName)
        mesurmentNumber = 1
        if (not os.path.exists(fileDir)):
            print(f"Creating directory: {fileDir}")
            os.mkdir(fileDir)
        if (not os.path.exists(FileName)):
            file = open(FileName, "w")
            file.write(
                "T_A[K] T_B[K] Setpoint[K] SR860x[V] SR860y[V] SR860f[Hz] SR860sin[V] SR860tht[deg] SR860phs[deg] SR860mgn[V] HTR CNT yyyy-mm-dd hh:mm:ss.ccccc")
            file.close()
        mainFolder = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..', 'UtilityFiles'))
        Stabilizer = TemperatureStabilizer(LakeShore331,os.path.join(mainFolder,"Stabilization.json"),nb_points_stabilisation=self.NumOfStabPoints,
                                           sampling_time=self.SplTime,tolerance_A=self.SlopeTolerance,tolerance_B=self.InterceptTolerance),

        for temperature in temperatures:
            Stabilizer.set_Setpoint(temperature)
            self.Lakeshore.write(f"SETP 1,{temperature}")
            while not Stabilizer.check_stabilization():
                pass
            parameters = self.__GetFullParametersList()
            file = open(FileName,'a')
            file.write(" ".join(parameters) + "\n")
            file.close()

        pass