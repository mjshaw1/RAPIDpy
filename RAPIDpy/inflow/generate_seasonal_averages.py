# -*- coding: utf-8 -*-
##
##  generate_seasonal_averages.py
##  RAPIDpy
##
##  Created by Alan D. Snow
##  License: BSD-3 Clause

from calendar import isleap
import multiprocessing
from netCDF4 import Dataset
import numpy as np
from time import gmtime

from ..dataset import RAPIDDataset

def generate_single_seasonal_average(args):
    """
    This function calculates the seasonal average for a single day of the year
    for all river segments
    """
    qout_file = args[0]
    seasonal_average_file = args[1]
    day_of_year = args[2]
    mp_lock = args[3]

    min_day = day_of_year - 3
    max_day = day_of_year + 3

    with RAPIDDataset(qout_file) as qout_nc_file: 
        time_indices = []
        for idx, t in enumerate(qout_nc_file.get_time_array()):
            var_time = gmtime(t)
            #move day back one past because of leap year adds 
            #a day after feb 29 (day 60)
            if isleap(var_time.tm_year) and var_time.tm_yday > 60:
                var_time.tm_yday -= 1
            #check if date within range of season
            if var_time.tm_yday >= min_day and var_time.tm_yday < max_day:
                time_indices.append(idx)
    
        if not time_indices:
            raise IndexError("No time steps found within range ...")
        
        streamflow_array = qout_nc_file.get_qout(time_index_array=time_indices)
    
        avg_streamflow_array = np.mean(streamflow_array, axis=1)
        std_streamflow_array = np.std(streamflow_array, axis=1)

        mp_lock.acquire()
        return_period_nc = Dataset(seasonal_average_file, 'a')
        return_period_nc.variables['average_flow'][day_of_year-1] = avg_streamflow_array
        return_period_nc.variables['std_dev_flow'][day_of_year-1] = std_streamflow_array
        return_period_nc.close()
        mp_lock.release()

def generate_seasonal_averages(qout_file, seasonal_average_file, 
                               num_cpus=multiprocessing.cpu_count()):
    """
    This function loops through a CF compliant rapid streamflow
    file to produce a netCDF file with a seasonal average for
    365 days a year
    """
    
    with RAPIDDataset(qout_file) as qout_nc_file:
        print("Setting up Seasonal Average File ...")
        seasonal_avg_nc = Dataset(seasonal_average_file, 'w')
        
        seasonal_avg_nc.createDimension('rivid', qout_nc_file.size_river_id)
        seasonal_avg_nc.createDimension('day_of_year', 365)

        timeSeries_var = seasonal_avg_nc.createVariable('rivid', 'i4', ('rivid',))
        timeSeries_var.long_name = (
            'Unique NHDPlus COMID identifier for each river reach feature')

        average_flow_var = seasonal_avg_nc.createVariable('average_flow', 'f8', ('rivid','day_of_year'))
        average_flow_var.long_name = 'seasonal average streamflow'
        average_flow_var.units = 'm3/s'
        
        std_dev_flow_var = seasonal_avg_nc.createVariable('std_dev_flow', 'f8', ('rivid','day_of_year'))
        std_dev_flow_var.long_name = 'seasonal std. dev. streamflow'
        std_dev_flow_var.units = 'm3/s'

        lat_var = seasonal_avg_nc.createVariable('lat', 'f8', ('rivid',),
                                                  fill_value=-9999.0)
        lat_var.long_name = 'latitude'
        lat_var.standard_name = 'latitude'
        lat_var.units = 'degrees_north'
        lat_var.axis = 'Y'

        lon_var = seasonal_avg_nc.createVariable('lon', 'f8', ('rivid',),
                                                  fill_value=-9999.0)
        lon_var.long_name = 'longitude'
        lon_var.standard_name = 'longitude'
        lon_var.units = 'degrees_east'
        lon_var.axis = 'X'

        seasonal_avg_nc.variables['lat'][:] = qout_nc_file.qout_nc.variables['lat'][:]
        seasonal_avg_nc.variables['lon'][:] = qout_nc_file.qout_nc.variables['lon'][:]

        river_id_list = qout_nc_file.get_river_id_array()
        seasonal_avg_nc.variables['rivid'][:] = river_id_list
        seasonal_avg_nc.close()
        
    #generate multiprocessing jobs
    mp_lock = multiprocessing.Manager().Lock()
    job_combinations = []
    for day_of_year in range(1, 366):
        job_combinations.append((qout_file,
                                 seasonal_average_file,
                                 day_of_year, 
                                 mp_lock
                                 ))

    pool = multiprocessing.Pool(num_cpus)
    pool.map(generate_single_seasonal_average,
             job_combinations)
    pool.close()
    pool.join()
