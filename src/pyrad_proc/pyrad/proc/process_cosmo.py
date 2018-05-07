"""
pyrad.proc.process_cosmo
===========================

Functions to manage COSMO data

.. autosummary::
    :toctree: generated/

    process_cosmo
    process_hzt
    process_cosmo_lookup_table
    process_hzt_lookup_table
    process_cosmo_coord
    process_hzt_coord

"""

from copy import deepcopy
from warnings import warn
import time
import glob

import numpy as np
from netCDF4 import num2date

import pyart

from ..io.io_aux import get_datatype_fields, find_raw_cosmo_file
from ..io.io_aux import find_hzt_file, get_fieldname_pyart
from ..io.read_data_cosmo import read_cosmo_data, read_cosmo_coord
from ..io.read_data_cosmo import cosmo2radar_data, cosmo2radar_coord
from ..io.read_data_cosmo import get_cosmo_fields
from ..io.read_data_radar import interpol_field
from ..io.read_data_hzt import read_hzt_data, hzt2radar_data, hzt2radar_coord
from ..io.read_data_hzt import get_iso0_field


def process_cosmo(procstatus, dscfg, radar_list=None):
    """
    Gets COSMO data and put it in radar coordinates

    Parameters
    ----------
    procstatus : int
        Processing status: 0 initializing, 1 processing volume,
        2 post-processing
    dscfg : dictionary of dictionaries
        data set configuration. Accepted Configuration Keywords::

        datatype : string. Dataset keyword
            arbitrary data type
        keep_in_memory : int. Dataset keyword
            if set keeps the COSMO data dict, the COSMO coordinates dict and
            the COSMO field in radar coordinates in memory
        regular_grid : int. Dataset keyword
            if set it is assume that the radar has a grid constant in time and
            there is no need to compute a new COSMO field if the COSMO
            data has not changed
        cosmo_type : str. Dataset keyword
            name of the COSMO field to process. Default TEMP
        cosmo_variables : list of strings. Dataset keyword
            Py-art name of the COSMO fields. Default temperature
    radar_list : list of Radar objects
        Optional. list of radar objects

    Returns
    -------
    new_dataset : Radar
        radar object
    ind_rad : int
        radar index

    """
    if procstatus != 1:
        return None, None

    # debugging
    # start_time = time.time()

    for datatypedescr in dscfg['datatype']:
        radarnr, datagroup, datatype, dataset, product = get_datatype_fields(
            datatypedescr)
        break

    ind_rad = int(radarnr[5:8])-1
    if radar_list[ind_rad] is None:
        warn('No valid radar')
        return None, None
    radar = radar_list[ind_rad]

    keep_in_memory = dscfg.get('keep_in_memory', 0)
    regular_grid = dscfg.get('regular_grid', 0)

    cosmo_type = dscfg.get('cosmo_type', 'TEMP')
    if cosmo_type == 'TEMP':
        field_names = ['temperature']
        if 'cosmo_variables' in dscfg:
            field_names = []
            for var in dscfg['cosmo_variables']:
                field_names.append(get_fieldname_pyart(var))
        zmin = None
    elif cosmo_type == 'WIND':
        field_names = ['wind_speed', 'wind_direction', 'vertical_wind_shear']
        if 'cosmo_variables' in dscfg:
            field_names = []
            for var in dscfg['cosmo_variables']:
                field_names.append(get_fieldname_pyart(var))
        zmin = None
    else:
        warn('Unknown COSMO data type '+cosmo_type)
        return None, None

    fname = find_raw_cosmo_file(dscfg['timeinfo'], cosmo_type, dscfg,
                                ind_rad=ind_rad)

    if fname is None:
        return None, None

    if keep_in_memory:
        if dscfg['initialized'] == 0:
            cosmo_coord = read_cosmo_coord(
                dscfg['cosmopath'][ind_rad] +
                'rad2cosmo1/cosmo-1_MDR_3D_const.nc', zmin=zmin)
            dscfg['global_data'] = {
                'cosmo_fname': None,
                'cosmo_data': None,
                'cosmo_fields': None,
                'time_index': None,
                'cosmo_coord': cosmo_coord}
            dscfg['initialized'] = 1

        cosmo_coord = dscfg['global_data']['cosmo_coord']
        if fname != dscfg['global_data']['cosmo_fname']:
            # debugging
            # start_time2 = time.time()
            cosmo_data = read_cosmo_data(
                fname, field_names=field_names, celsius=True)
            # print(" reading COSMO takes %s seconds " %
            #      (time.time() - start_time2))
            if cosmo_data is None:
                warn('COSMO data not found')
                return None, None

            dscfg['global_data']['cosmo_data'] = cosmo_data
            dscfg['global_data']['cosmo_fname'] = fname
        else:
            print('raw COSMO data already in memory')
            cosmo_data = dscfg['global_data']['cosmo_data']
    else:
        cosmo_coord = read_cosmo_coord(
            dscfg['cosmopath'][ind_rad]+'rad2cosmo1/cosmo-1_MDR_3D_const.nc',
            zmin=zmin)

        # debugging
        # start_time2 = time.time()
        cosmo_data = read_cosmo_data(
            fname, field_names=field_names, celsius=True)
        # print(" reading COSMO takes %s seconds " %
        #      (time.time() - start_time2))
        if cosmo_data is None:
            warn('COSMO data not found')
            return None, None

    dtcosmo = num2date(
        cosmo_data['time']['data'][:], cosmo_data['time']['units'])
    time_index = np.argmin(abs(dtcosmo-dscfg['timeinfo']))

    if keep_in_memory and regular_grid:
        if time_index != dscfg['global_data']['time_index']:
            cosmo_fields = cosmo2radar_data(
                radar, cosmo_coord, cosmo_data, time_index=time_index,
                field_names=field_names)
            if cosmo_fields is None:
                warn('Unable to obtain COSMO fields')
                return None, None

            dscfg['global_data']['time_index'] = time_index
            dscfg['global_data']['cosmo_fields'] = cosmo_fields
        else:
            print('COSMO field already in memory')
            cosmo_fields = dscfg['global_data']['cosmo_fields']
    else:
        cosmo_fields = cosmo2radar_data(
            radar, cosmo_coord, cosmo_data, time_index=time_index,
            field_names=field_names)
        if cosmo_fields is None:
            warn('Unable to obtain COSMO fields')
            return None, None

    # prepare for exit
    new_dataset = deepcopy(radar)
    new_dataset.fields = dict()

    for field in cosmo_fields:
        for field_name in field:
            new_dataset.add_field(field_name, field[field_name])

    return new_dataset, ind_rad


def process_hzt(procstatus, dscfg, radar_list=None):
    """
    Gets iso0 degree data in HZT format and put it in radar coordinates

    Parameters
    ----------
    procstatus : int
        Processing status: 0 initializing, 1 processing volume,
        2 post-processing
    dscfg : dictionary of dictionaries
        data set configuration. Accepted Configuration Keywords::

        datatype : string. Dataset keyword
            arbitrary data type
        keep_in_memory : int. Dataset keyword
            if set keeps the COSMO data dict, the COSMO coordinates dict and
            the COSMO field in radar coordinates in memory
        regular_grid : int. Dataset keyword
            if set it is assume that the radar has a grid constant in time and
            there is no need to compute a new COSMO field if the COSMO
            data has not changed
        cosmo_type : str. Dataset keyword
            name of the COSMO field to process. Default TEMP
        cosmo_variables : list of strings. Dataset keyword
            Py-art name of the COSMO fields. Default temperature
    radar_list : list of Radar objects
        Optional. list of radar objects

    Returns
    -------
    new_dataset : Radar
        radar object
    ind_rad : int
        radar index

    """
    if procstatus != 1:
        return None, None

    # debugging
    # start_time = time.time()

    for datatypedescr in dscfg['datatype']:
        radarnr, datagroup, datatype, dataset, product = get_datatype_fields(
            datatypedescr)
        break

    ind_rad = int(radarnr[5:8])-1
    if radar_list[ind_rad] is None:
        warn('No valid radar')
        return None, None
    radar = radar_list[ind_rad]

    keep_in_memory = dscfg.get('keep_in_memory', 0)
    regular_grid = dscfg.get('regular_grid', 0)

    fname = find_hzt_file(dscfg['timeinfo'], dscfg, ind_rad=ind_rad)

    if fname is None:
        return None, None

    if keep_in_memory:
        if dscfg['initialized'] == 0:
            hzt_data = read_hzt_data(fname)
            if hzt_data is None:
                warn('HZT data not found')
                return None, None
            hzt_coord = {
                'x': hzt_data['x'],
                'y': hzt_data['y']
            }
            dscfg['global_data'] = {
                'hzt_fname': None,
                'hzt_data': None,
                'iso0_field': None,
                'time_index': None,
                'hzt_coord': hzt_coord}
            dscfg['initialized'] = 1

        hzt_coord = dscfg['global_data']['hzt_coord']
        if fname != dscfg['global_data']['hzt_fname']:
            hzt_data = read_hzt_data(fname)
            if hzt_data is None:
                warn('HZT data not found')
                return None, None

            dscfg['global_data']['hzt_data'] = hzt_data
            dscfg['global_data']['hzt_fname'] = fname
        else:
            print('raw HZT data already in memory')
            hzt_data = dscfg['global_data']['hzt_data']
    else:
        hzt_data = read_hzt_data(fname)
        if hzt_data is None:
            warn('HZT data not found')
            return None, None
        hzt_coord = {
            'x': hzt_data['x'],
            'y': hzt_data['y']
        }
        if hzt_data is None:
            warn('HZT data not found')
            return None, None

    dthzt = num2date(
        hzt_data['time']['data'][:], hzt_data['time']['units'])
    time_index = np.argmin(abs(dthzt-dscfg['timeinfo']))

    if keep_in_memory and regular_grid:
        if time_index != dscfg['global_data']['time_index']:
            iso0_field = hzt2radar_data(radar, hzt_coord, hzt_data)
            if iso0_field is None:
                warn('Unable to obtain heigth over iso0 field')
                return None, None

            dscfg['global_data']['time_index'] = time_index
            dscfg['global_data']['iso0_field'] = iso0_field
        else:
            print('HZT field already in memory')
            iso0_field = dscfg['global_data']['iso0_field']
    else:
        iso0_field = hzt2radar_data(radar, hzt_coord, hzt_data)
        if iso0_field is None:
            warn('Unable to obtain HZT fields')
            return None, None

    # prepare for exit
    new_dataset = deepcopy(radar)
    new_dataset.fields = dict()
    new_dataset.add_field('height_over_iso0', iso0_field)

    return new_dataset, ind_rad


def process_cosmo_lookup_table(procstatus, dscfg, radar_list=None):
    """
    Gets COSMO data and put it in radar coordinates
    using look up tables computed or loaded when initializing

    Parameters
    ----------
    procstatus : int
        Processing status: 0 initializing, 1 processing volume,
        2 post-processing
    dscfg : dictionary of dictionaries
        data set configuration. Accepted Configuration Keywords::

        datatype : string. Dataset keyword
            arbitrary data type
        lookup_table : int. Dataset keyword
            if set a pre-computed look up table for the COSMO coordinates is
            loaded. Otherwise the look up table is computed taking the first
            radar object as reference
        regular_grid : int. Dataset keyword
            if set it is assume that the radar has a grid constant in time and
            therefore there is no need to interpolate the COSMO field in
            memory to the current radar grid
        cosmo_type : str. Dataset keyword
            name of the COSMO field to process. Default TEMP
        cosmo_variables : list of strings. Dataset keyword
            Py-art name of the COSMO fields. Default temperature
    radar_list : list of Radar objects
        Optional. list of radar objects

    Returns
    -------
    new_dataset : Radar
        radar object
    ind_rad : int
        radar index

    """
    if procstatus != 1:
        return None, None

    # debugging
    # start_time = time.time()

    for datatypedescr in dscfg['datatype']:
        radarnr, datagroup, datatype, dataset, product = get_datatype_fields(
            datatypedescr)
        break

    ind_rad = int(radarnr[5:8])-1
    if radar_list[ind_rad] is None:
        warn('No valid radar')
        return None, None
    radar = radar_list[ind_rad]

    regular_grid = dscfg.get('regular_grid', 0)
    lookup_table = dscfg.get('lookup_table', 0)

    cosmo_type = dscfg.get('cosmo_type', 'TEMP')
    if cosmo_type == 'TEMP':
        field_names = ['temperature']
        if 'cosmo_variables' in dscfg:
            field_names = []
            for var in dscfg['cosmo_variables']:
                field_names.append(get_fieldname_pyart(var))
        zmin = None
    elif cosmo_type == 'WIND':
        field_names = ['wind_speed', 'wind_direction', 'vertical_wind_shear']
        if 'cosmo_variables' in dscfg:
            field_names = []
            for var in dscfg['cosmo_variables']:
                field_names.append(get_fieldname_pyart(var))
        zmin = None
    else:
        warn('Unknown COSMO data type '+cosmo_type)
        return None, None

    fname = find_raw_cosmo_file(dscfg['timeinfo'], cosmo_type, dscfg,
                                ind_rad=ind_rad)

    if fname is None:
        return None, None

    if dscfg['initialized'] == 0:
        if lookup_table:
            savedir = dscfg['cosmopath'][ind_rad]+'rad2cosmo1/'
            fname_ind = 'rad2cosmo_cosmo_index_'+dscfg['procname']+'.nc'
            fname_ind2 = glob.glob(savedir+fname_ind)
            if not fname_ind2:
                warn('File '+savedir+fname_ind+' not found')
                return None, None
            else:
                cosmo_radar = pyart.io.read_cfradial(fname_ind2[0])
        else:
            cosmo_coord = read_cosmo_coord(
                dscfg['cosmopath'][ind_rad] +
                'rad2cosmo1/cosmo-1_MDR_3D_const.nc', zmin=zmin)
            cosmo_ind_field = cosmo2radar_coord(radar, cosmo_coord)
            cosmo_radar = deepcopy(radar)
            cosmo_radar.fields = dict()
            cosmo_radar.add_field('cosmo_index', cosmo_ind_field)

        dscfg['global_data'] = {
            'cosmo_fname': None,
            'cosmo_data': None,
            'cosmo_fields': None,
            'cosmo_radar': cosmo_radar,
            'time_index': None}
        dscfg['initialized'] = 1

    if fname != dscfg['global_data']['cosmo_fname']:
        # debugging
        # start_time2 = time.time()
        cosmo_data = read_cosmo_data(
            fname, field_names=field_names, celsius=True)
        # print(" reading COSMO takes %s seconds " %
        #      (time.time() - start_time2))
        if cosmo_data is None:
            warn('COSMO data not found')
            return None, None

        dscfg['global_data']['cosmo_data'] = cosmo_data
    else:
        print('raw COSMO data already in memory')
        cosmo_data = dscfg['global_data']['cosmo_data']

    dtcosmo = num2date(
        cosmo_data['time']['data'][:], cosmo_data['time']['units'])

    time_index = np.argmin(abs(dtcosmo-dscfg['timeinfo']))

    if (fname != dscfg['global_data']['cosmo_fname'] or
            time_index != dscfg['global_data']['time_index']):
        # debugging
        # start_time3 = time.time()
        cosmo_fields = get_cosmo_fields(
            cosmo_data,
            dscfg['global_data']['cosmo_radar'].fields['cosmo_index'],
            time_index=time_index,
            field_names=field_names)
        if cosmo_fields is None:
            warn('Unable to obtain COSMO fields')
            return None, None
        # print(" getting COSMO data takes %s seconds "
        #      % (time.time() - start_time3))

        dscfg['global_data']['time_index'] = time_index
        dscfg['global_data']['cosmo_fields'] = cosmo_fields
    else:
        print('COSMO field already in memory')
        cosmo_fields = dscfg['global_data']['cosmo_fields']

    dscfg['global_data']['cosmo_fname'] = fname

    # prepare for exit
    new_dataset = deepcopy(radar)
    new_dataset.fields = dict()

    if not regular_grid:
        radar_aux = deepcopy(dscfg['global_data']['cosmo_radar'])
        radar_aux.fields = dict()

    for field in cosmo_fields:
        for field_name in field:
            try:
                if regular_grid:
                    new_dataset.add_field(field_name, field[field_name])
                else:
                    # interpolate to current radar grid
                    radar_aux.add_field(field_name, field[field_name])
                    cosmo_field_interp = interpol_field(
                        radar, radar_aux, field_name)
                    new_dataset.add_field(field_name, cosmo_field_interp)
            except Exception as ee:
                warn(str(ee))
                warn('Unable to add COSMO '+field_name +
                     ' field to radar object')
                return None, None

    return new_dataset, ind_rad


def process_hzt_lookup_table(procstatus, dscfg, radar_list=None):
    """
    Gets HZT data and put it in radar coordinates
    using look up tables computed or loaded when initializing

    Parameters
    ----------
    procstatus : int
        Processing status: 0 initializing, 1 processing volume,
        2 post-processing
    dscfg : dictionary of dictionaries
        data set configuration. Accepted Configuration Keywords::

        datatype : string. Dataset keyword
            arbitrary data type
        lookup_table : int. Dataset keyword
            if set a pre-computed look up table for the COSMO coordinates is
            loaded. Otherwise the look up table is computed taking the first
            radar object as reference
        regular_grid : int. Dataset keyword
            if set it is assume that the radar has a grid constant in time and
            therefore there is no need to interpolate the COSMO field in
            memory to the current radar grid
    radar_list : list of Radar objects
        Optional. list of radar objects

    Returns
    -------
    new_dataset : Radar
        radar object
    ind_rad : int
        radar index

    """
    if procstatus != 1:
        return None, None

    # debugging
    # start_time = time.time()

    for datatypedescr in dscfg['datatype']:
        radarnr, datagroup, datatype, dataset, product = get_datatype_fields(
            datatypedescr)
        break

    ind_rad = int(radarnr[5:8])-1
    if radar_list[ind_rad] is None:
        warn('No valid radar')
        return None, None
    radar = radar_list[ind_rad]

    regular_grid = dscfg.get('regular_grid', 0)
    lookup_table = dscfg.get('lookup_table', 0)

    fname = find_hzt_file(dscfg['timeinfo'], dscfg, ind_rad=ind_rad)

    if fname is None:
        return None, None

    if dscfg['initialized'] == 0:
        if lookup_table:
            savedir = dscfg['cosmopath'][ind_rad]+'rad2cosmo1/'
            fname_ind = 'rad2cosmo_hzt_index_'+dscfg['procname']+'.nc'
            fname_ind2 = glob.glob(savedir+fname_ind)
            if not fname_ind2:
                warn('File '+savedir+fname_ind+' not found')
                return None, None
            else:
                hzt_radar = pyart.io.read_cfradial(fname_ind2[0])
        else:
            hzt_data = read_hzt_data(fname)
            if hzt_data is None:
                warn('HZT data not found')
                return None, None
            hzt_coord = {
                'x': hzt_data['x'],
                'y': hzt_data['y']
            }
            hzt_ind_field = hzt2radar_coord(radar, hzt_coord)
            hzt_radar = deepcopy(radar)
            hzt_radar.fields = dict()
            hzt_radar.add_field('hzt_index', hzt_ind_field)

        dscfg['global_data'] = {
            'hzt_fname': None,
            'hzt_data': None,
            'iso0_field': None,
            'hzt_radar': hzt_radar,
            'time_index': None}
        dscfg['initialized'] = 1

    if fname != dscfg['global_data']['hzt_fname']:
        hzt_data = read_hzt_data(fname)
        if hzt_data is None:
            warn('HZT data not found')
            return None, None

        dscfg['global_data']['hzt_data'] = hzt_data
    else:
        print('HZT data already in memory')
        hzt_data = dscfg['global_data']['hzt_data']

    dthzt = num2date(
        hzt_data['time']['data'][:], hzt_data['time']['units'])
    time_index = np.argmin(abs(dthzt-dscfg['timeinfo']))

    if (fname != dscfg['global_data']['hzt_fname'] or
            time_index != dscfg['global_data']['time_index']):
        # debugging
        # start_time3 = time.time()
        iso0_field = get_iso0_field(
            hzt_data, dscfg['global_data']['hzt_radar'].fields['hzt_index'],
            dscfg['global_data']['hzt_radar'].gate_altitude['data'])
        if iso0_field is None:
            warn('Unable to obtain height over iso0')
            return None, None

        dscfg['global_data']['time_index'] = time_index
        dscfg['global_data']['iso0_field'] = iso0_field
    else:
        print('HZT field already in memory')
        iso0_field = dscfg['global_data']['iso0_field']

    dscfg['global_data']['hzt_fname'] = fname

    # prepare for exit
    new_dataset = deepcopy(radar)
    new_dataset.fields = dict()

    if not regular_grid:
        radar_aux = deepcopy(dscfg['global_data']['hzt_radar'])
        radar_aux.fields = dict()

    try:
        if regular_grid:
            new_dataset.add_field('height_over_iso0', iso0_field)
        else:
            # interpolate to current radar grid
            radar_aux.add_field('height_over_iso0', iso0_field)
            hzt_field_interp = interpol_field(
                radar, radar_aux, 'height_over_iso0')
            new_dataset.add_field('height_over_iso0', hzt_field_interp)
    except Exception as ee:
        warn(str(ee))
        warn('Unable to add height_over_iso0 ' +
             ' field to radar object')
        return None, None

    return new_dataset, ind_rad


def process_cosmo_coord(procstatus, dscfg, radar_list=None):
    """
    Gets the COSMO indices corresponding to each cosmo coordinates

    Parameters
    ----------
    procstatus : int
        Processing status: 0 initializing, 1 processing volume,
        2 post-processing
    dscfg : dictionary of dictionaries
        data set configuration. Accepted Configuration Keywords::

        datatype : string. Dataset keyword
            arbitrary data type
        cosmopath : string. General keyword
            path where to store the look up table
    radar_list : list of Radar objects
        Optional. list of radar objects

    Returns
    -------
    new_dataset : Radar
        radar object
    ind_rad : int
        radar index

    """
    if procstatus != 1:
        return None, None

    start_time = time.time()

    if dscfg['initialized'] == 1:
        return None, None

    for datatypedescr in dscfg['datatype']:
        radarnr, datagroup, datatype, dataset, product = get_datatype_fields(
            datatypedescr)
        break

    ind_rad = int(radarnr[5:8])-1
    if radar_list[ind_rad] is None:
        warn('No valid radar')
        return None, None
    radar = radar_list[ind_rad]

    cosmo_coord = read_cosmo_coord(
        dscfg['cosmopath'][ind_rad]+'rad2cosmo1/cosmo-1_MDR_3D_const.nc',
        zmin=None)

    if cosmo_coord is None:
        return None, None

    cosmo_ind_field = cosmo2radar_coord(
        radar, cosmo_coord, slice_xy=True, slice_z=False)

    # prepare for exit
    radar_obj = deepcopy(radar)
    radar_obj.fields = dict()
    radar_obj.add_field('cosmo_index', cosmo_ind_field)

    new_dataset = {
        'ind_rad': ind_rad,
        'radar_obj': radar_obj}

    dscfg['initialized'] = 1

    return new_dataset, ind_rad


def process_hzt_coord(procstatus, dscfg, radar_list=None):
    """
    Gets the HZT indices corresponding to each HZT coordinates

    Parameters
    ----------
    procstatus : int
        Processing status: 0 initializing, 1 processing volume,
        2 post-processing
    dscfg : dictionary of dictionaries
        data set configuration. Accepted Configuration Keywords::

        datatype : string. Dataset keyword
            arbitrary data type
        cosmopath : string. General keyword
            path where to store the look up table
    radar_list : list of Radar objects
        Optional. list of radar objects

    Returns
    -------
    new_dataset : Radar
        radar object
    ind_rad : int
        radar index

    """
    if procstatus != 1:
        return None, None

    start_time = time.time()

    if dscfg['initialized'] == 1:
        return None, None

    for datatypedescr in dscfg['datatype']:
        radarnr, datagroup, datatype, dataset, product = get_datatype_fields(
            datatypedescr)
        break

    ind_rad = int(radarnr[5:8])-1
    if radar_list[ind_rad] is None:
        warn('No valid radar')
        return None, None
    radar = radar_list[ind_rad]

    fname = find_hzt_file(dscfg['timeinfo'], dscfg, ind_rad=ind_rad)

    hzt_data = read_hzt_data(fname)
    if hzt_data is None:
        warn('HZT data not found')
        return None, None
    hzt_coord = {
        'x': hzt_data['x'],
        'y': hzt_data['y']
    }

    hzt_ind_field = hzt2radar_coord(radar, hzt_coord)

    # prepare for exit
    radar_obj = deepcopy(radar)
    radar_obj.fields = dict()
    radar_obj.add_field('hzt_index', hzt_ind_field)

    new_dataset = {
        'ind_rad': ind_rad,
        'radar_obj': radar_obj}

    dscfg['initialized'] = 1

    return new_dataset, ind_rad
