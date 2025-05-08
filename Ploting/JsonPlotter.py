import json
import matplotlib.pyplot as plt
import matplotlib.animation as animate
import sys
import numpy as np
class JsonPlotter:
    def __init__(self,fileName:str):
        self.Figure:plt.figure = plt.figure()
        self.FileName: str = fileName
        self.Plot = self.Figure.add_subplot()
        self.Plot.set_xlabel('Mesurment number')
        self.Plot.set_ylabel('Temperature')

        self.Figure.tight_layout()
        self.ToleranceLines = []
        for i,label in zip(range(3),["Setpoint","Tolerance",""]):
            line = self.Plot.axhline(color='g' if i ==0 else 'r',label = label)
            self.ToleranceLines.append(line)
        self.Points, = self.Plot.plot([],[],linewidth=0,marker='o',label='Measured points')
        self.FitedLine, = self.Plot.plot([],[],label='Fitted line')
        self.Plot.legend()
    def __HandlePlots(self,i):
        file = open(self.FileName,'r')
        jsondata = json.load(file)
        file.close()
        lastMeasurment = jsondata["cycles_history"][-1]
        tolerancepoints = [jsondata['setpoint'],jsondata['setpoint'] + jsondata['tolerance_B'],jsondata['setpoint'] - jsondata['tolerance_B']]
        pts: list = lastMeasurment['measurements']
        x = np.arange(len(pts))
        for line,tolerancepoint in zip(self.ToleranceLines,tolerancepoints ):
            line.set_data(x,[tolerancepoint])
        self.Points.set_data(x,pts)
        self.FitedLine.set_data(x,lastMeasurment['slope_A']*x + lastMeasurment['intercept_B'])
        self.Plot.relim()
        self.Plot.autoscale_view()
        self.Figure.tight_layout()

    def startPlot(self)-> None:
        """_summary_
        Starts a plot
        """
        try:
            live_plot = animate.FuncAnimation(self.Figure,self.__HandlePlots,cache_frame_data=False,interval=1000)
            plt.show()
        except KeyboardInterrupt:
            print('Plotting stopped by user.')
if(__name__ =='__main__'):
    plot = JsonPlotter(sys.argv[1])
    # print("aaaa")
    plot.startPlot()