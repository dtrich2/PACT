import sys
import numpy as np
import math
import os
import re
class SPICE_transientSolver:
    def __init__(self,name,num_core,ll_solver,step_size,total_time,ptrace_step_size,UIC,ambient):
        self.name = name
        self.num_core = num_core
        self.ll_solver = ll_solver
        self.step_size = step_size
        self.total_time = total_time
        self.UIC = UIC

        # use to define the pwl current function step size
        self.ptrace_step_size = ptrace_step_size
        self.ambient = ambient
        return
    # Display solver name function
    def display_solver(self):
        print(self.name)
        return
    # Temperature-dependent simulation framework update function
    def update(self):
        self.cooData.fill(0)
        self.cooX.fill(0)
        self.cooY.fill(0)
        for (layer,prop) in self.dict_properties_update['update'].items():
            if(prop=='Rz'):
                self.dict_properties['Rz'].update(self.dict_properties_update["Rz"])
                self.Rz.update(self.dict_properties_update['Rz'])
            elif(prop=='Rx'):
                self.dict_properties['Rx'].update(self.dict_properties_update["Rx"])
                self.Rx.update(self.dict_properties_update['Rx'])
            elif(prop=='Ry'):
                self.dict_properties['Ry'].update(self.dict_properties_update["Ry"])
                self.Ry.update(self.dict_properties_update['Ry'])
            elif(prop=='C'):
                self.dict_properties['C'].update(self.dict_properties_update["C"])
                self.C.update(self.dict_properties_update['C'])
            elif(prop=='I'):
                self.dict_properties['I'].update(self.dict_properties_update["I"])
                self.I.update(self.dict_properties_update['I'])
                for key,value in self.I.items():
                    self.b = np.append(self.b,value.flatten())
                self.b = np.reshape(self.b,(self.size,1))
        return
    # Setup function for solver
    def setup(self):
        self.nr = int(self.dict_properties['grid_rows'])
        self.nc = int(self.dict_properties['grid_cols'])
        self.nl = int(self.dict_properties['num_layers'])
        self.layerVN = self.dict_properties['layer_virtual_nodes']
        self.factorVN = self.dict_properties['factor_virtual_nodes']
        self.r_amb= self.dict_properties['r_amb']
        self.size= self.nl * self.nr * self.nc
        self.col_limit = self.nc - 1
        self.row_limit = self.nr - 1
        self.layer_limit = self.nl - 1
        self.nnz = self.nl * self.nr * self.nc + 2 * (self.nl-1) * self.nr * self.nc + 2 * self.nl * (self.nr-1) * \
            self.nc +  2 * self.nl * self.nr * (self.nc-1)
        self.addY={0:1,1:-1,2:-self.nc,3:self.nc,4:-self.nr*self.nc,5:self.nr*self.nc} # 0...6 correspond to [Re,Rw,Rn,Rs,Ra,Rb]
        self.prod = self.nr*self.nc

        self.cooData = np.zeros((self.nnz))
        self.cooX = np.zeros((self.nnz))
        self.cooY = np.zeros((self.nnz))
        self.Rx = self.dict_properties['Rx']
        self.Ry = self.dict_properties['Ry']
        self.Rz = self.dict_properties['Rz']
        self.C = self.dict_properties['C']
        self.I = self.dict_properties['I']
        self.Conv = self.dict_properties['Conv']
        self.glabels = self.dict_properties['g2bmap']
        self.liq_layer = []
        self.heatsink_layer = []
        self.heatsink = None
        self.heatspreader = None
        self.heatsink_others = {}
        self.heatspreader_others = {}
        for layer,label in self.glabels.items():
            if 'Liq' in label:
                self.liq_layer.append(layer)
        for layer,label in self.glabels.items():
            if 'HeatSink' in label:
                self.heatsink_layer.append(layer)
        if len(self.heatsink_layer)!=0:
            self.heatspreader = self.heatsink_layer[0] 
            self.heatsink = self.heatsink_layer[1] 
            self.heatsink_others = self.dict_properties['others'][self.heatsink]
            self.heatspreader_others = self.dict_properties['others'][self.heatspreader]
        for item in self.dict_properties['others'].items():
            for key in item[1].keys():
                if key == 'inlet_T_constant':
                    self.inlet_T_constant=float(item[1][key]) 
        self.r_amb_reciprocal = 1/self.r_amb
        self.I_avg = {}
        for key,value in self.I.items():
            self.I_avg[key] = np.mean(value,axis=0)
        return
    # Solve the thermal RC matrices and return the grid temperatures
    def getTemperature(self,dict_properties, logFile=None,SpiceFile=None,SpiceResultFile=None,mode=None):
        res = [] 
        if(mode==None):
            self.dict_properties = dict_properties
            self.setup()
        elif(mode=='temperature_dependent'):
            self.dict_properties_update = dict_properties
            self.update()
        with open(SpiceFile,'w') as myfile:
                myfile.write(".title spice transient solver\n")
                if self.UIC=="True":
                        print("initFile: "+SpiceFile+".ic")
                        myfile.write(f".INCLUDE {SpiceFile}.ic\n")
                myfile.write(f"Vg GND 0 {self.ambient}\n")
                if 'inlet_T_constant' in self.dict_properties['others'][1].keys():
                   myfile.write(f"Vin INLET 0 {self.inlet_T_constant+273.15}\n")

                curidx=0
                for grididx in range(self.size):
                    layer = int(grididx / self.prod)
                    row = int((grididx - layer*self.prod)/self.nc) 
                    col = int( grididx - (layer*(self.prod)+row*self.nc))
                    if (col > 0):
                        Rw = self.Rx[layer][row][col-1]/2 + self.Rx[layer][row][col]/2
                    else:
                        Rw = 100000000
                    if(col < (self.col_limit)):
                        Re = self.Rx[layer][row][col+1]/2 + self.Rx[layer][row][col]/2
                    else:
                        Re = 100000000
                    if(row > 0):
                        Rn = self.Ry[layer][row-1][col]/2 + self.Ry[layer][row][col]/2
                    else:
                        Rn = 10000000
                    if(row < self.row_limit):
                        Rs = self.Ry[layer][row+1][col]/2 + self.Ry[layer][row][col]/2
                    else:
                        Rs = 10000000
                    if(layer > 0):
                        Ra = float(self.factorVN[self.layerVN[layer-1]])*self.Rz[layer-1][row][col] + \
                        (1-float(self.factorVN[self.layerVN[layer]]))*self.Rz[layer][row][col]
                    else:
                        Ra = 100000000

                    if(layer < self.layer_limit):
                        Rb = float(self.factorVN[self.layerVN[layer]])*self.Rz[layer][row][col] + \
                        (1-float(self.factorVN[self.layerVN[layer+1]]))*self.Rz[layer+1][row][col]
                    elif layer == self.heatsink:
                        Rb = float(self.factorVN[self.layerVN[layer]])*self.Rz[layer][row][col]
                    else: 
                        Rb = 100000000
                    #current:
                    if layer!= self.layer_limit and layer!=self.heatspreader and self.I_avg[layer][row][col]!=0:
                        i = 1
                        if len(self.I[layer])>1:
                            text = "I_{}_{}_{} GND Node{}_{}_{} PWL(0s 0A".format(layer,row,col,layer, row, col)
                            temp = re.compile("([0-9.]+)([a-zA-Z]+)")
                            res = temp.match(self.ptrace_step_size).groups()
                            step_size = float(temp.match(self.step_size).groups()[0])
                            ptrace_step_size = float(temp.match(self.ptrace_step_size).groups()[0])
                            if step_size<ptrace_step_size:
                                text+=f" {(i)*float(res[0])}{res[1]} 0A {(i)*float(res[0])+step_size}{res[1]} {self.I[layer][i-1][row][col]}A"
                                i+=1
                            elif step_size>ptrace_step_size:
                                raise Exception("Error: solver step size is larger than power step size")
                            while i<=len(self.I[layer]):
                                temp = re.compile("([0-9.]+)([a-zA-Z]+)")
                                res = temp.match(self.ptrace_step_size).groups()
                                if step_size<ptrace_step_size:
                                    text+=f" {(i)*float(res[0])}{res[1]} {self.I[layer][i-2][row][col]}A {(i)*float(res[0])+step_size}{res[1]} {self.I[layer][i-1][row][col]}A"
                                else:
                                    text+=f" {(i)*float(res[0])}{res[1]} {self.I[layer][i-1][row][col]}A"

                                i+=1
                            text+=")\n"
                            myfile.write(text)
                        elif layer!=self.heatspreader and self.I_avg[layer][row][col]!=0:
                            myfile.write("I_{}_{}_{} GND Node{}_{}_{} PULSE(0 {}A 0s 0s 0s {} {})\n".format(layer,row,col,layer, row, col, self.I[layer][0][row][col],self.total_time,self.total_time))
                    #east resistance
                    if col != self.col_limit:
                        myfile.write("R_{}_{}_{}_1 Node{}_{}_{} Node{}_{}_{} {}\n".format(layer,row,col,layer, row, col,layer,row,col+1,Re))
                    #Heat Spreader right
                    if col == self.col_limit and layer==self.heatspreader:
                        myfile.write("Rsp_{}_{}_{}_1 Node{}_{}_{} Node_sp_right {}\n".format(layer,row,col,layer, row, col,self.Rx[layer][row][col]/2+self.row_limit*self.heatspreader_others['r_sp1_x_constant']))
                    #Heat Sink right
                    if col == self.col_limit and layer==self.heatsink:
                        myfile.write("Rhs_{}_{}_{}_1 Node{}_{}_{} Node_hs_right {}\n".format(layer,row,col,layer, row, col,self.Rx[layer][row][col]/2+self.row_limit*self.heatsink_others['r_hs1_x_constant']))
                    #Heat Spreader left
                    if col == 0 and layer==self.heatspreader:
                        myfile.write("Rsp_{}_{}_{}_1 Node{}_{}_{} Node_sp_left {}\n".format(layer,row,col,layer, row, col,self.Rx[layer][row][col]/2+self.row_limit*self.heatspreader_others['r_sp1_x_constant']))
                    #Heat Sink left
                    if col == 0 and layer==self.heatsink:
                        myfile.write("Rhs_{}_{}_{}_1 Node{}_{}_{} Node_hs_right {}\n".format(layer,row,col,layer, row, col,self.Rx[layer][row][col]/2+self.row_limit*self.heatsink_others['r_hs1_x_constant']))
                    #north resistance
                    if row != self.row_limit:
                        #not liquid grid cell
                        if self.glabels[layer][row][col]!='Liq':
                            myfile.write("R_{}_{}_{}_2 Node{}_{}_{} Node{}_{}_{} {}\n".format(layer,row,col,layer, row, col,layer,row+1,col,Rs))
                        #liquid grid cell
                        else:
                            if row == 0:
                                #inlet
                                myfile.write("G_%d_%d_%d INLET Node%d_%d_%d INLET 0 %s\n"%(layer,row,col,layer,row,col,self.Conv[layer][row][col]))
                                #channel
                            else:
                                myfile.write("G_%d_%d_%d Node%d_%d_%d Node%d_%d_%d VALUE = {(V(Node%d_%d_%d)+V(Node%d_%d_%d))/2*%s}\n"%(layer,row,col,layer,row-1,col,layer,row,col,layer,row-1,col,layer,row,col,self.Conv[layer][row][col]))
                    if row == self.row_limit and self.glabels[layer][row][col] == 'Liq':
                        #last channel
                        myfile.write("G_%d_%d_%d Node%d_%d_%d Node%d_%d_%d VALUE = {(V(Node%d_%d_%d)+V(Node%d_%d_%d))/2*%s}\n"%(layer,row,col,layer,row-1,col,layer,row,col,layer,row-1,col,layer,row,col,self.Conv[layer][row][col]))
                        #outlet
                        myfile.write("G_%d_%d_%d Node%d_%d_%d INLET Node%d_%d_%d 0 %s\n"%(layer,row+1,col,layer,row,col,layer,row,col,self.Conv[layer][row][col]))

                    #Heat spreader top
                    if row == self.row_limit and layer==self.heatspreader:
                        myfile.write("Rsp_{}_{}_{}_2 Node{}_{}_{} Node_sp_top {}\n".format(layer,row,col,layer, row, col,self.Ry[layer][row][col]/2+self.col_limit*self.heatspreader_others['r_sp1_y_constant']))
                    #Heat sink top
                    if row == self.row_limit and layer==self.heatsink:
                        myfile.write("Rhs_{}_{}_{}_2 Node{}_{}_{} Node_hs_top {}\n".format(layer,row,col,layer, row, col,self.Ry[layer][row][col]/2+self.col_limit*self.heatsink_others['r_hs1_y_constant']))
                    #Heat spreader bot
                    if row == 0 and layer==self.heatspreader:
                        myfile.write("Rsp_{}_{}_{}_2 Node{}_{}_{} Node_sp_bot {}\n".format(layer,row,col,layer, row, col,self.Ry[layer][row][col]/2+self.col_limit*self.heatspreader_others['r_sp1_y_constant']))
                    #Heat sink top
                    if row == 0 and layer==self.heatsink:
                        myfile.write("Rhs_{}_{}_{}_2 Node{}_{}_{} Node_hs_bot {}\n".format(layer,row,col,layer, row, col,self.Ry[layer][row][col]/2+self.col_limit*self.heatsink_others['r_hs1_y_constant']))
                    #above resistance
                    if layer != self.layer_limit: 
                        myfile.write("R_{}_{}_{}_3 Node{}_{}_{} Node{}_{}_{} {}\n".format(layer,row,col,layer, row, col,layer+1,row,col,Rb))
                    elif layer!=self.heatsink:
                        myfile.write("R_{}_{}_{}_3 Node{}_{}_{} GND {}\n".format(layer,row,col,layer, row, col,self.r_amb))
                    elif layer==self.heatsink:
                        myfile.write("R_{}_{}_{}_3 Node{}_{}_{} GND {}\n".format(layer,row,col,layer, row, col,Rb))
                    myfile.write("C_{}_{}_{} Node{}_{}_{} GND {}\n".format(layer,row,col,layer,row, col, self.C[layer][row][col]))
                if len(self.heatsink_layer)!=0:
                    #add heat spreader to heat sink inner node
                    myfile.write(f"R_sp_hs_in_left Node_sp_left Node_hs_in_left {self.heatspreader_others['r_sp_per_x_constant']}")
                    myfile.write('\n')
                    myfile.write(f"R_sp_hs_in_right Node_sp_right Node_hs_in_right {self.heatspreader_others['r_sp_per_x_constant']}")
                    myfile.write('\n')
                    myfile.write(f"R_sp_hs_in_top Node_sp_top Node_hs_in_top {self.heatspreader_others['r_sp_per_y_constant']}")
                    myfile.write('\n')
                    myfile.write(f"R_sp_hs_in_bot Node_sp_bot Node_hs_in_bot {self.heatspreader_others['r_sp_per_y_constant']}")
                    myfile.write('\n')
                    #add heat hinfk inner to heat sink outter node
                    myfile.write(f"R_hs_hs_left Node_hs_in_left Node_hs_out_left {self.heatsink_others['r_hs2_x_constant']+self.heatsink_others['r_hs_constant']}")
                    myfile.write('\n')
                    myfile.write(f"R_hs_hs_right Node_hs_in_right Node_hs_out_right {self.heatsink_others['r_hs2_x_constant']+self.heatsink_others['r_hs_constant']}")
                    myfile.write('\n')
                    myfile.write(f"R_hs_hs_top Node_hs_in_top Node_hs_out_top {self.heatsink_others['r_hs2_y_constant']+self.heatsink_others['r_hs_constant']}")
                    myfile.write('\n')
                    myfile.write(f"R_hs_hs_bot Node_hs_in_bot Node_hs_out_bot {self.heatsink_others['r_hs2_y_constant']+self.heatsink_others['r_hs_constant']}")
                    myfile.write('\n')
                    #add heat sink to ambient R
                    myfile.write(f"R_hs_amb_in_left Node_hs_in_left GND {self.heatsink_others['r_hs_c_per_x_constant']+self.heatsink_others['r_amb_c_per_x_constant']}")
                    myfile.write('\n')
                    myfile.write(f"R_hs_amb_in_right Node_hs_in_right GND {self.heatsink_others['r_hs_c_per_x_constant']+self.heatsink_others['r_amb_c_per_x_constant']}")
                    myfile.write('\n')
                    myfile.write(f"R_hs_amb_in_top Node_hs_in_top GND {self.heatsink_others['r_hs_c_per_y_constant']+self.heatsink_others['r_amb_c_per_y_constant']}")
                    myfile.write('\n')
                    myfile.write(f"R_hs_amb_in_bot Node_hs_in_bot GND {self.heatsink_others['r_hs_c_per_y_constant']+self.heatsink_others['r_amb_c_per_y_constant']}")
                    myfile.write('\n')
                    myfile.write(f"R_hs_amb_out_left Node_hs_out_left GND {self.heatsink_others['r_hs_per_constant']+self.heatsink_others['r_amb_per_constant']}")
                    myfile.write('\n')
                    myfile.write(f"R_hs_amb_out_right Node_hs_out_right GND {self.heatsink_others['r_hs_per_constant']+self.heatsink_others['r_amb_per_constant']}")
                    myfile.write('\n')
                    myfile.write(f"R_hs_amb_out_top Node_hs_out_top GND {self.heatsink_others['r_hs_per_constant']+self.heatsink_others['r_amb_per_constant']}")
                    myfile.write('\n')
                    myfile.write(f"R_hs_amb_out_bot Node_hs_out_bot GND {self.heatsink_others['r_hs_per_constant']+self.heatsink_others['r_amb_per_constant']}")
                    myfile.write('\n')



                    #add capaciatance for extra package node
                    myfile.write("C_sp_per_y_top Node_sp_top GND {}\n".format(self.heatspreader_others['c_sp_per_y_constant']))
                    myfile.write("C_sp_per_y_bot Node_sp_bot GND {}\n".format(self.heatspreader_others['c_sp_per_y_constant']))
                    myfile.write("C_sp_per_x_left Node_sp_left GND {}\n".format(self.heatspreader_others['c_sp_per_x_constant']))
                    myfile.write("C_sp_per_x_right Node_sp_right GND {}\n".format(self.heatspreader_others['c_sp_per_x_constant']))
                    myfile.write("C_hs_c_per_y_top Node_hs_in_top GND {}\n".format(self.heatsink_others['c_hs_c_per_y_constant']))
                    myfile.write("C_hs_c_per_y_bot Node_hs_in_bot GND {}\n".format(self.heatsink_others['c_hs_c_per_y_constant']))
                    myfile.write("C_hs_c_per_x_left Node_hs_in_left GND {}\n".format(self.heatsink_others['c_hs_c_per_x_constant']))
                    myfile.write("C_hs_c_per_x_right Node_hs_in_right GND {}\n".format(self.heatsink_others['c_hs_c_per_x_constant']))
                    myfile.write("C_hs_per_top Node_hs_out_top GND {}\n".format(self.heatsink_others['c_hs_per_constant']))
                    myfile.write("C_hs_per_bot Node_hs_out_bot GND {}\n".format(self.heatsink_others['c_hs_per_constant']))
                    myfile.write("C_hs_per_left Node_hs_out_left GND {}\n".format(self.heatsink_others['c_hs_per_constant']))
                    myfile.write("C_hs_per_right Node_hs_out_right GND {}\n".format(self.heatsink_others['c_hs_per_constant']))
                    myfile.write("C_amb_per_top Node_hs_out_top GND {}\n".format(self.heatsink_others['c_amb_per_constant']))
                    myfile.write("C_amb_per_bot Node_hs_out_bot GND {}\n".format(self.heatsink_others['c_amb_per_constant']))
                    myfile.write("C_amb_per_left Node_hs_out_left GND {}\n".format(self.heatsink_others['c_amb_per_constant']))
                    myfile.write("C_amb_per_right Node_hs_out_right GND {}\n".format(self.heatsink_others['c_amb_per_constant']))
                    myfile.write("C_amb_per_in_top Node_hs_in_top GND {}\n".format(self.heatsink_others['c_amb_per_constant']))
                    myfile.write("C_amb_per_in_bot Node_hs_in_bot GND {}\n".format(self.heatsink_others['c_amb_per_constant']))
                    myfile.write("C_amb_per_in_left Node_hs_in_left GND {}\n".format(self.heatsink_others['c_amb_per_constant']))
                    myfile.write("C_amb_per_in_right Node_hs_in_right GND {}\n".format(self.heatsink_others['c_amb_per_constant']))
            




                if self.UIC=="True":
                    myfile.write(f'.TRAN {self.step_size} {self.total_time} UIC\n')
                else:
                    myfile.write(f'.TRAN {self.step_size} {self.total_time}\n')

                '''disable zorltan for mono3D simualtion (useful for solving the linear system partitioning probelm)
                To solve the iterative solver never converge problem, we force the LINSOL TYPE to be KLU.
                However, to achieve the best performance, TYPE option can be eliminated and Xyce will automatically
                select the LINSOL solver based on the problem size.'''
                myfile.write(f'.OPTIONS LINSOL TYPE=KLU TR_PARTITION=0 \n')
                # enable flat round robin device partitioning (useful for device partitioning problem)
                myfile.write(f'.OPTIONS DIST STRATEGY=2\n')
                myfile.write(f'.OPTIONS TIMEINT METHOD={self.ll_solver}\n')
                myfile.write(f'.OPTIONS OUTPUT INITIAL_INTERVAL={self.step_size} {self.total_time}\n')
                myfile.write('.PRINT TRAN FORMAT=CSV PRECISION=4 ')
                for grididx in range(self.size):
                    layer = int(grididx / self.prod)
                    row = int((grididx - layer*self.prod)/self.nc) 
                    col = int( grididx - (layer*(self.prod)+row*self.nc))
                    myfile.write("V(Node{}_{}_{}) ".format(layer,row,col))
                myfile.write("\n")
                myfile.write(".SAVE TYPE=IC\n")
                myfile.write(".end\n")
        if int(self.num_core)<=1:
            os.system(f"Xyce -l {logFile} {SpiceFile}")
        else:
            os.system(f"mpirun -np {self.num_core} Xyce -l {logFile} {SpiceFile}")
        with open(SpiceResultFile,'r') as myfile:
            tmp = np.asarray(list(map(float,list(myfile)[-1][:].split(',')[1:])))
            reshape_x = tmp.reshape(self.nl,self.nr,self.nc)
        return reshape_x
