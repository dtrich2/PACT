import sys, argparse,  os
from argparse import Namespace
import configparser
from configparser import NoSectionError, NoOptionError
import pandas as pd
import numpy as np
from ChipStack import ChipStack
from GridManager import GridManager
from SuperLUSolver import SuperLUSolver
from SPICESolver_steady import SPICE_steadySolver
from SPICESolver_transient import SPICE_transientSolver

def gridTemperatureToFile(arr, layer_num, gridSteadyFile):
    arr_flat = np.round(arr.flatten(),6)
    L_df = pd.DataFrame(arr_flat)
    L_df.to_csv(gridSteadyFile+".layer"+str(layer_num),header=False)

def gridTemp2File(arr, gridSteadyFile, counter):
    #global counter
    np.savetxt(gridSteadyFile+".layer"+str(counter), arr, delimiter="\n",fmt="%.2f")
    #counter += 1

def display_df_dict():
    print ('------------ Config File Data stored as dictionary (Showing \'Si\' in default config file) ----------------')
    print (config.sections())
    print (config._sections['Si'])
    print ('\n\n------------ ModelParams Data also stored as dictionary (Showing \'Grid\' in the modelParams File ----------------')
    print (modelParams._sections['Grid'])
    print ('\n\n------------ LCF Data stored as a panda frame ----------------')
    print (lcf_df)
    print ('\n\n------------ INIT Temperature is of double datatype ----------------')
    print (initTemp)
    print ('-------------------------------------------------------------\n\n')

def display_args():
    print ('------------ Printing command line arguments ----------------')
    print ('lcfFile:',lcfFile)
    print ('configFile:',configFile)
    print ('modelParamsFile:',modelParamsFile)
    print ('initFile:',initFile)
    print ('steadyFile:',steadyFile)
    print ('gridSteadyFile:',gridSteadyFile)
    print ('-------------------------------------------------------------\n\n')

###################!!! Default Paths to the LCF, ModelParams, ad config files !!!#########
#home_path = '/home/prachis/GitHub/CRI-Cooling-Tool/' # <- Edit this only based on tool's home directory
"""
home_path = './../' #One directory up
lcf_path = home_path+'lcf_files/'
lib_path = home_path+'lib/'
config_path = home_path+'config_files/'
modelParams_path = home_path+'modelParams_files/'
init_path = home_path+'init_files/'
steady_path = home_path+'steady_files/'
ptrace_path = home_path+'ptrace_files/'
results_path = home_path+'results/'
heatMaps_path = home_path+'results/heat_maps/'
"""

def do_parsing():
    ######! Command-Line Arguments Description !######
    parser = argparse.ArgumentParser(prog='PACT',)
    parser.add_argument('lcfFile',action='store')
    parser.add_argument('configFile', action='store')
    parser.add_argument('modelParamsFile', action='store')
    parser.add_argument('--init', action='store',dest='initFile')
    parser.add_argument('--steady', action='store',dest='steadyFile')
    parser.add_argument('--gridSteadyFile', action='store',dest='gridSteadyFile')
    parser_args =parser.parse_args()
    return (parser_args.configFile, parser_args.gridSteadyFile, parser_args.initFile, parser_args.lcfFile, parser_args.modelParamsFile, parser_args.steadyFile)

def PACT(configFile, gridSteadyFile, initFile, lcfFile, modelParamsFile, steadyFile):
    parser_args=Namespace(configFile=configFile, gridSteadyFile=gridSteadyFile, initFile=initFile, lcfFile=lcfFile, modelParamsFile=modelParamsFile, steadyFile=steadyFile)
    lcfFile = parser_args.lcfFile
    defaultConfigFile = parser_args.configFile
    modelParamsFile = parser_args.modelParamsFile
    gridSteadyFile = parser_args.gridSteadyFile
    gridtransientFile = '.'.join(parser_args.gridSteadyFile.split('.')[:-2])+'.block.transient.csv'
    logFile = '.'.join(parser_args.gridSteadyFile.split('.')[:-2])+'.log'
    SpiceFile = '.'.join(parser_args.gridSteadyFile.split('.')[:-2])+'.cir'
    SpiceResultFile = '.'.join(parser_args.gridSteadyFile.split('.')[:-2])+'.cir.csv'
    os.system(f"rm -rf {gridtransientFile}")
    if (parser_args.initFile is not None):
        initFile = parser.parse_args().initFile
    else:
        initFile = None
    if (parser_args.steadyFile is not None):
        steadyFile = parser_args.steadyFile
    else:
        steadyFile = None

    ######! Read Layer File !######
    thickness_layers={}
    try:
        lcf_df = pd.read_csv(lcfFile, lineterminator="\n")
        if(lcf_df['Thickness (m)'].isnull().values.any()):
            print('Error:','Thickness (m) must be specified for each layer')
            sys.exit(2)
        thickness_layers=lcf_df.set_index("Layer").to_dict()["Thickness (m)"]
        if(lcf_df['FloorplanFile'].isnull().values.any()):
            print('Error:','Floorplan File must be specified for each layer')
            sys.exit(2)
    except FileNotFoundError:
        print('Error:','Layer File does not exist:',lcfFile)
        sys.exit(2)

    ######! Read Default config file !######
    ### Default read format: ordered dictionary ###
    defaultConfig = configparser.ConfigParser()
    try:
        defaultConfig.read(defaultConfigFile)
    except FileNotFoundError:
        print('Error:','Config File does not exist:',configFile)
        sys.exit(2)

    ######! Read ModelParams file !######
    global modelParams
    modelParams = configparser.ConfigParser()
    try:
        modelParams.read(modelParamsFile)
    except FileNotFoundError:
        print('Error:','ModelParams File does not exist:',modelParamsFile)
        sys.exit(2)

    #####! Add a noPackage Layer !####
    num_layers = lcf_df['Layer'].max()
    lcf_df.loc[:,'VerticalHeatFlow']=True #Add Vetical True for all other layers
    if "NoPackage" in modelParams:
        noPackage_layer = pd.DataFrame([],columns=['FloorplanFile','Layer','PtraceFile','LateralHeatFlow','VerticalHeatFlow','Thickness (m)'])
        noPackage_layer.loc[0,'FloorplanFile']=lcf_df.loc[num_layers,'FloorplanFile']
        noPackage_layer.loc[0,'Layer']=num_layers+1
        noPackage_layer.loc[0,'PtraceFile']=None
        noPackage_layer.loc[0,'LateralHeatFlow']=modelParams.get('NoPackage','LateralHeatFlow')
        noPackage_layer.loc[0,'VerticalHeatFlow']=modelParams.get('NoPackage','VerticalHeatFlow')
        noPackage_layer.loc[0,'Thickness (m)']=defaultConfig.get('NoPackage','thickness (m)')
        noPackage_layer.loc[0,'ConfigFile']=defaultConfigFile
        lcf_df = lcf_df.append(noPackage_layer,sort=False)
        thickness_layers[num_layers+1] = float(defaultConfig.get('NoPackage','thickness (m)'))
    if "HeatSink" in modelParams:
        HeatSpreader_layer = pd.DataFrame([],columns=['FloorplanFile','Layer','PtraceFile','LateralHeatFlow','VerticalHeatFlow','Thickness (m)'])
        HeatSpreader_layer.loc[0,'FloorplanFile']=lcf_df.loc[num_layers,'FloorplanFile']
        HeatSpreader_layer.loc[0,'Layer']=num_layers+1
        HeatSpreader_layer.loc[0,'PtraceFile']=None
        HeatSpreader_layer.loc[0,'LateralHeatFlow']=modelParams.get('HeatSink','LateralHeatFlow')
        HeatSpreader_layer.loc[0,'VerticalHeatFlow']=modelParams.get('HeatSink','VerticalHeatFlow')
        HeatSpreader_layer.loc[0,'Thickness (m)']=defaultConfig.get('HeatSink','heatspreader_thickness (m)')
        HeatSpreader_layer.loc[0,'ConfigFile']=defaultConfigFile
        lcf_df = lcf_df.append(HeatSpreader_layer,sort=False,ignore_index=True)
        thickness_layers[num_layers+1] = float(defaultConfig.get('HeatSink','heatsink_thickness (m)'))
        HeatSink_layer = pd.DataFrame([],columns=['FloorplanFile','Layer','PtraceFile','LateralHeatFlow','VerticalHeatFlow','Thickness (m)'])
        HeatSink_layer.loc[0,'FloorplanFile']=lcf_df.loc[num_layers,'FloorplanFile']
        HeatSink_layer.loc[0,'Layer']=num_layers+2
        HeatSink_layer.loc[0,'PtraceFile']=None
        HeatSink_layer.loc[0,'LateralHeatFlow']=modelParams.get('HeatSink','LateralHeatFlow')
        HeatSink_layer.loc[0,'VerticalHeatFlow']=modelParams.get('HeatSink','VerticalHeatFlow')
        HeatSink_layer.loc[0,'Thickness (m)']=defaultConfig.get('HeatSink','heatsink_thickness (m)')
        HeatSink_layer.loc[0,'ConfigFile']=defaultConfigFile
        lcf_df = lcf_df.append(HeatSink_layer,sort=False,ignore_index=True)
        thickness_layers[num_layers+2] = float(defaultConfig.get('HeatSink','heatsink_thickness (m)'))

    ######! Check for missing data !######
    ### Read all unique floorplan files names ###
    flp_files = lcf_df['FloorplanFile'].unique()

    ### Create tuples of config_file and floorplan_file to check if the details of the  materials to be modeled are present ###
    config_label_df = pd.DataFrame()
    for ff in flp_files:
        try:
            ff_df = pd.read_csv(ff)
        except FileNotFoundError:
            print('Error: Floorplan file not found',ff)
            sys.exit(2)

        config_label_df = config_label_df.append(ff_df[['ConfigFile','Label']].drop_duplicates(), ignore_index=True)
    config_label_df.drop_duplicates(inplace=True)
    config_label_df['ConfigFile'] = config_label_df['ConfigFile'].fillna(defaultConfigFile)

    config_label_dict = {k: g["Label"].tolist() for k,g in config_label_df.groupby("ConfigFile")}
    if "NoPackage" in modelParams:
        config_label_dict[defaultConfigFile] = config_label_dict[defaultConfigFile] + ['NoPackage']
    if "HeatSink" in modelParams:
        config_label_dict[defaultConfigFile] = config_label_dict[defaultConfigFile] + ['HeatSink']

    list_of_labels = config_label_df['Label'].unique()
    if "NoPackage" in modelParams:
        list_of_labels = np.append(list_of_labels,['NoPackage'],axis=0)
    if "HeatSink" in modelParams:
        list_of_labels = np.append(list_of_labels,['HeatSink'],axis=0)

    virtual_node_labels = {x: modelParams.get(x,'virtual_node') for x  in list_of_labels}
    label_mode = {x: modelParams.get(x,'mode') for x in list_of_labels}

    ### Ordered dictionary with all material properties from the specified config file ###
    MaterialProp_dict = {}
    label_properties_dict = {}
    for ll in list_of_labels:
        ######! Read Config file !######
        try:
            lib_location = modelParams.get(ll,'library')
            ######Below contains all libraries that should be imported###
            #lib_dict[ll]=lib_location.split(".")[0]
        except NoOptionError:
            print('ERROR: Library (used for thermal modeling) not defined for the label \'',ll, '\'')
            sys.exit(2)
        try:
            lib_name = modelParams.get(ll,'library_name')
            if(lib_name==''):
                print('ERROR: Library_name is null for the label \'',ll, '\'')
                sys.exit(2)
            lib = modelParams[lib_name]
        except NoOptionError:
            print('ERROR: Library_name not defined for the label \'',ll, '\'')
            sys.exit(2)
        except KeyError:
            print('ERROR: Section \'',lib_name,'\'not defined for the label \'',ll, '\'')
            sys.exit(2)
        try:
            label_properties_dict[ll]=modelParams.get(lib_name,'properties')
        except (NoOptionError, KeyError):
            print("\'properties\' not defined for the label",ll,"in the modelParams file")
            sys.exit(2)

    ######! Check for missing data !######
    label_prop_dict={}
    config = configparser.ConfigParser()
    for cf in config_label_dict.keys():
        ######! Read Config file !######
        if(cf == defaultConfigFile):
            config = defaultConfig
        else:
            config.read(cf)
        for l in config_label_dict[cf]:
            try:
                properties = [option for option in config[l]]
                properties_needed = [x.strip() for x in label_properties_dict[l].split(',')]
                label_prop_dict[l]=properties_needed

                MaterialProp_dict.update({(cf,l): config._sections[l]})
                if not (set(properties_needed).issubset(set(properties))):
                    print("ERROR: Mising information about \'", section,"\'in",cf)
                    print("Please ensure all the properties in the modelParams file are specified in the config file.")
                    sys.exit(2)

            except (NoSectionError):
                print('ERROR: Label \'',l ,'\' not defined in ',cf)
                sys.exit(2)
    ### Read initFile ###
    if (initFile is None):
        val, unit = defaultConfig['Init']['Temperature'].split()
        if (unit=='K' or unit == 'Kelvin'):
            initTemp = float(val)
        elif (unit=='C' or 'Celsius'):
            initTemp = float(val) - 273.15
    else:
        initTemp = pd.read_csv(initFile,lineterminator="\n")
    chipStack = ChipStack(lcf_df,defaultConfig,initTemp,defaultConfigFile,virtual_node_labels)
    ###Call grid manager ###
    gridManager = GridManager(modelParams._sections['Grid'])
    label_config_dict = dict.fromkeys([(x,y) for y in config_label_dict.keys() for x in config_label_dict[y]])
    gridManager.add_label_config_mode_dict(label_config_dict,config,label_mode)
    ###Create Chip stack###
    chipStack = gridManager.createGrids(chipStack,label_config_dict)
    #######SOLVER#####
    ambient_T = config._sections['Init'].get('ambient')
    ambient_T = float(ambient_T.split(' ')[0])
    global solver
    if modelParams._sections['Solver'].get('name') == 'SuperLU':
        #print("high-level solver = SuperLU")
        exec("solver = %sSolver(modelParams._sections['Solver'].get('name'))" % (modelParams._sections['Solver'].get('name')), globals())

    elif  modelParams._sections['Solver'].get('name') == 'SPICE_steady':
        #print("high-level solver = SPICE_steady")
        #print(f"low-level solver = {modelParams._sections['Solver'].get('ll_steady_solver')}")
        exec("solver = %sSolver(modelParams._sections['Solver'].get('name'),%s,modelParams._sections['Solver'].get('ll_steady_solver'),%s)" % (modelParams._sections['Solver'].get('name'),modelParams._sections['Simulation'].get('number_of_core'),ambient_T), globals())

    elif  modelParams._sections['Solver'].get('name') == 'SPICE_transient':
        print("high-level solver = SPICE_transient")
        os.system("rm -rf RC_transient_block_temp.csv")
        print(f"low-level solver = {modelParams._sections['Solver'].get('ll_transient_solver')}")
        exec("solver = %sSolver(modelParams._sections['Solver'].get('name'),%s,modelParams._sections['Solver'].get('ll_transient_solver'),modelParams._sections['Simulation'].get('step_size'),modelParams._sections['Simulation'].get('total_simulation_time'),modelParams._sections['Simulation'].get('ptrace_step_size'),modelParams._sections['Simulation'].get('init_file'),%s)" % (modelParams._sections['Solver'].get('name'),modelParams._sections['Simulation'].get('number_of_core'),ambient_T ), globals())

    grid_rows=modelParams._sections['Grid'].get('rows')
    grid_cols=modelParams._sections['Grid'].get('cols')
    num_layers = chipStack.num_layers

    solver_properties={'grid_rows':grid_rows,'grid_cols':grid_cols,'num_layers':num_layers}
    dict_Rx = {chipStack.Layers_data[x].layer_num:chipStack.Layers_data[x].Rx for x in chipStack.Layers_data.keys()}
    dict_Ry = {chipStack.Layers_data[x].layer_num:chipStack.Layers_data[x].Ry for x in chipStack.Layers_data.keys()}
    dict_Rz = {chipStack.Layers_data[x].layer_num:chipStack.Layers_data[x].Rz for x in chipStack.Layers_data.keys()}
    dict_C = {chipStack.Layers_data[x].layer_num:chipStack.Layers_data[x].C for x in chipStack.Layers_data.keys()}
    dict_I = {chipStack.Layers_data[x].layer_num:chipStack.Layers_data[x].I for x in chipStack.Layers_data.keys()}
    dict_Conv = {chipStack.Layers_data[x].layer_num:chipStack.Layers_data[x].Conv for x in chipStack.Layers_data.keys()}
    dict_others = {chipStack.Layers_data[x].layer_num:chipStack.Layers_data[x].others for x in chipStack.Layers_data.keys()}
    dict_g2bmap = {chipStack.Layers_data[x].layer_num:chipStack.Layers_data[x].g2bmap for x in chipStack.Layers_data.keys()}
    dict_virtual_nodes = {chipStack.Layers_data[x].layer_num:chipStack.Layers_data[x].virtual_node for x in chipStack.Layers_data.keys()}
    # Ensure there is no singular R matrix 
    for key,value in dict_Rx.items():
        value[value==0.0]=1e-6
    for key,value in dict_Ry.items():
        value[value==0.0]=1e-6
    for key,value in dict_Rz.items():
        value[value==0.0]=1e-6
    solver_properties['Rx']=dict_Rx
    solver_properties['Ry']=dict_Ry
    solver_properties['Rz']=dict_Rz
    solver_properties['C']=dict_C
    solver_properties['I']=dict_I
    solver_properties['Conv']=dict_Conv
    solver_properties['others']=dict_others
    solver_properties['g2bmap']=dict_g2bmap
    solver_properties['others']=dict_others
    solver_properties['layer_virtual_nodes']=dict_virtual_nodes
    solver_properties['factor_virtual_nodes']=modelParams._sections['VirtualNodes']
    solver_properties['r_amb']=chipStack.Layers_data[num_layers-1].r_amb
    ###Solver RC matrics###
    if solver.name=="SuperLU":
      grid_temperature = solver.getTemperature(solver_properties)
    else:
      grid_temperature = solver.getTemperature(solver_properties,logFile,SpiceFile,SpiceResultFile)
    if(str(modelParams.get('Simulation','temperature_dependent'))=='True'):
        mode = 'temperature_dependent'
        count = 0
        convergence = float(modelParams.get('Simulation','convergence'))
        deltaT = convergence + 1
        deltaLayer = 1
        hybrid_wick_properties = MaterialProp_dict[(defaultConfigFile,"HybridWick")]
        grid_length = gridManager.grid_length
        grid_width = gridManager.grid_width
        lcf_df.set_index('Layer',inplace=True)
        thickness = thickness_layers[deltaLayer] 
    ###Temperature-dependent simulation framework###
        while(deltaT > convergence):
            grid_temperature_old = np.copy(grid_temperature[deltaLayer])
            solver_properties = LibTemperatureDependent.getTemperatureDependentProperties(grid_length,\
                grid_width,thickness,grid_temperature_old,hybrid_wick_properties)
            grid_temperature = solver.getTemperature(solver_properties,mode)
            deltaT = np.max(abs(grid_temperature[deltaLayer] - grid_temperature_old))
            count += 1
            if(count == 100):
                print("ERROR: No Convergence")
                sys.exit(2)
        
        print("num iterations:",count)
    # Map grid to block
    if modelParams._sections['Solver'].get('name') == 'SPICE_transient':
         with open(SpiceResultFile,"r")as myfile:
             for num, lines in enumerate(myfile):
                 if num>1:
                     tmp = np.asarray(list(map(float,lines.split(',')[1:])))
                     reshape = tmp.reshape(int(num_layers),int(grid_rows),int(grid_cols))
                     with open(gridtransientFile,"a") as myfile:
                         myfile.write("step "+str(num-1)+" ")
                     gridManager.grid2block(chipStack, reshape, modelParams.get('Grid','grid_mode'),transient=True,transientFile = gridtransientFile)
    
    gridManager.grid2block(chipStack, grid_temperature,modelParams.get('Grid','grid_mode'))
    grid_temperature  = grid_temperature.reshape(num_layers,-1)

    
    for layer in range(num_layers):
        gridTemp2File(grid_temperature[layer].reshape(-1), gridSteadyFile=gridSteadyFile, counter=layer)
    #global counter
    #counter = 0
    #np.apply_along_axis(gridTemp2File,1,grid_temperature, gridSteadyFile=gridSteadyFile)

if __name__ == "__main__":
    input_files=do_parsing()
    print(input_files)
    PACT(*input_files)

