"""
pyrad.flow.flow_control
=======================

functions to control the Pyrad data processing flow

.. autosummary::
    :toctree: generated/

    main
    _user_input_listener
    _generate_dataset
    _generate_dataset_mp
    _process_dataset
    _generate_prod
    _create_cfg_dict
    _create_datacfg_dict
    _create_dscfg_dict
    _create_prdcfg_dict
    _get_datatype_list
    _get_datasets_list
    _get_masterfile_list
    _add_dataset
    _warning_format

"""
from __future__ import print_function
import sys
import fcntl
import warnings
from warnings import warn
import traceback
import os
from datetime import datetime
from datetime import timedelta
import atexit
import inspect
import gc
import numpy as np
import multiprocessing as mp
import queue
import time
import threading

from ..io.config import read_config
from ..io.read_data_radar import get_data
from ..io.io_aux import get_datetime, get_file_list, get_scan_list
from ..io.io_aux import get_dataset_fields, get_datatype_fields
from ..io.trajectory import Trajectory

from ..proc.process_aux import get_process_func
from ..prod.product_aux import get_prodgen_func

from pyrad import proc, prod
from pyrad import version as pyrad_version
from pyart import version as pyart_version

MULTIPROCESSING_PROD = False
MULTIPROCESSING_DSET = False


def main(cfgfile, starttime, endtime, infostr="", trajfile="", rt=False):
    """
    main flow control. Processes data in real time or over a given
    period of time given either by the user or by the trajectory
    file.

    Parameters
    ----------
    cfgfile : str
        path of the main config file
    starttime, endtime : datetime object
        start and end time of the data to be processed
    trajfile : str
        path to file describing the trajectory
    infostr : str
        Information string about the actual data processing
        (e.g. 'RUN57'). This string is added to product files.

    """
    print("- PYRAD version: %s (compiled %s by %s)" %
          (pyrad_version.version, pyrad_version.compile_date_time,
           pyrad_version.username))
    print("- PYART version: " + pyart_version.version)

    # Define behaviour of warnings
    warnings.simplefilter('always')  # always print matching warnings
    # warnings.simplefilter('error')  # turn matching warnings into exceptions
    warnings.formatwarning = _warning_format  # define format

    # initialize listener for user input
    input_queue = queue.Queue()
    pinput = threading.Thread(
        name='user_input_listener', target=_user_input_listener, daemon=True,
        args=(input_queue, ))
    pinput.start()

    cfg = _create_cfg_dict(cfgfile)
    datacfg = _create_datacfg_dict(cfg)

    # Get the plane trajectory
    if (len(trajfile) > 0):
        print("- Trajectory file: " + trajfile)
        try:
            traj = Trajectory(trajfile, starttime=starttime, endtime=endtime)
        except Exception as ee:
            warn(str(ee))
            sys.exit(1)

        # Derive start and end time (if not specified by arguments)
        if (starttime is None):
            scan_min = cfg['ScanPeriod'] * 1.1  # [min]
            starttime = traj.get_start_time() - timedelta(minutes=scan_min)
        if (endtime is None):
            scan_min = cfg['ScanPeriod'] * 1.1  # [min]
            endtime = traj.get_end_time() + timedelta(minutes=scan_min)
    else:
        traj = None

    if (len(infostr) > 0):
        print('- Info string : ' + infostr)

    # get data types and levels
    datatypesdescr_list = list()
    for i in range(1, cfg['NumRadars']+1):
        datatypesdescr_list.append(
            _get_datatype_list(cfg, radarnr='RADAR'+'{:03d}'.format(i)))

    dataset_levels = _get_datasets_list(cfg)

    # if it is not real time and there are no volumes to process stop here
    if not rt:
        masterfilelist, masterdatatypedescr, masterscan = _get_masterfile_list(
            datatypesdescr_list[0], starttime, endtime, datacfg,
            scan_list=cfg['ScanList'])

        nvolumes = len(masterfilelist)
        if nvolumes == 0:
            raise ValueError(
                "ERROR: Could not find any valid volumes between " +
                starttime.strftime('%Y-%m-%d %H:%M:%S') + " and " +
                endtime.strftime('%Y-%m-%d %H:%M:%S') + " for " +
                "master scan '" + str(masterscan) +
                "' and master data type '" + masterdatatypedescr +
                "'")
        print('- Number of volumes to process: ' + str(nvolumes))

    # initial processing of the datasets
    print('- Initializing datasets:')

    dscfg = dict()
    for level in sorted(dataset_levels):
        print('-- Process level: '+level)
        if MULTIPROCESSING_DSET:
            jobs = []
            out_queue = mp.Queue()
            for dataset in dataset_levels[level]:
                dscfg.update({dataset: _create_dscfg_dict(cfg, dataset)})
                p = mp.Process(
                    name=dataset, target=_generate_dataset_mp,
                    args=(dataset, cfg, dscfg[dataset], out_queue),
                    kwargs={'proc_status': 0,
                            'radar_list': None,
                            'voltime': None,
                            'trajectory': traj,
                            'runinfo': infostr})
                jobs.append(p)
                p.start()

            # wait for completion of the jobs
            for job in jobs:
                job.join()
        else:
            for dataset in dataset_levels[level]:
                dscfg.update({dataset: _create_dscfg_dict(cfg, dataset)})
                new_dataset, ind_rad, jobs_ds = _generate_dataset(
                    dataset, cfg, dscfg[dataset], proc_status=0,
                    radar_list=None, voltime=None, trajectory=traj,
                    runinfo=infostr)

    # manual garbage collection after initial processing
    gc.collect()

    end_proc = False
    last_processed = None

    while not end_proc:
        # check if user has requested exit
        try:
            user_input = input_queue.get_nowait()
            end_proc = user_input
            warn('Program terminated by user')
            break
        except queue.Empty:
            pass

        # if real time update start and stop processing time and get list of
        # files to process
        if rt:
            nowtime = datetime.utcnow()

            # end time has been set and current time older than end time
            # quit processing
            if endtime is not None:
                if nowtime > endtime:
                    end_proc = True
                    break

            # start time has been set. Check if current time has to be
            # processed
            if starttime is not None:
                if nowtime < starttime:
                    continue

            endtime_loop = nowtime
            if last_processed is None:
                scan_min = cfg['ScanPeriod'] * 1.1  # [min]
                starttime_loop = endtime_loop - timedelta(minutes=scan_min)
            else:
                starttime_loop = last_processed + timedelta(seconds=10)

            masterfilelist, masterdatatypedescr, masterscan = (
                _get_masterfile_list(
                    datatypesdescr_list[0], starttime_loop, endtime_loop,
                    datacfg, scan_list=cfg['ScanList']))

        # check if there are no new files
        nvolumes = len(masterfilelist)
        if nvolumes == 0:
            continue

        # process all data files in file list
        for masterfile in masterfilelist:
            # check if user has requested exit
            try:
                user_input = input_queue.get_nowait()
                end_proc = user_input
                warn('Program terminated by user')
                break
            except queue.Empty:
                pass

            print('- master file: ' + os.path.basename(masterfile))
            master_voltime = get_datetime(masterfile, masterdatatypedescr)

            # check if it was already processed
            if last_processed is not None:
                if master_voltime < last_processed:
                    continue

            # get data of master radar
            radar_list = list()
            radar_list.append(
                get_data(master_voltime, datatypesdescr_list[0], datacfg))

            # get data of rest of radars
            for i in range(1, cfg['NumRadars']):
                filelist_ref, datatypedescr_ref, scan_ref = (
                    _get_masterfile_list(
                        datatypesdescr_list[i],
                        master_voltime-timedelta(seconds=cfg['TimeTol']),
                        master_voltime+timedelta(seconds=cfg['TimeTol']),
                        datacfg, scan_list=cfg['ScanList']))

                nfiles_ref = len(filelist_ref)
                if nfiles_ref == 0:
                    warn("ERROR: Could not find any valid volume for " +
                         " reference time " +
                         master_voltime.strftime('%Y-%m-%d %H:%M:%S') +
                         ' and radar RADAR'+'{:03d}'.format(i+1))
                    radar_list.append(None)
                elif nfiles_ref == 1:
                    voltime_ref = get_datetime(
                        filelist_ref[0], datatypedescr_ref)
                    radar_list.append(
                        get_data(voltime_ref, datatypesdescr_list[i], datacfg))
                else:
                    voltime_ref_list = []
                    for j in range(nfiles_ref):
                        voltime_ref_list.append(get_datetime(
                            filelist_ref[j], datatypedescr_ref))
                    voltime_ref = min(
                        voltime_ref_list, key=lambda x: abs(x-master_voltime))
                    radar_list.append(
                        get_data(voltime_ref, datatypesdescr_list[i], datacfg))

            # process all data sets
            jobs_prod = []
            for level in sorted(dataset_levels):
                print('-- Process level: '+level)
                if MULTIPROCESSING_DSET:
                    jobs = []
                    out_queue = mp.Queue()
                    for dataset in dataset_levels[level]:
                        p = mp.Process(
                            name=dataset, target=_generate_dataset_mp,
                            args=(dataset, cfg, dscfg[dataset], out_queue),
                            kwargs={'proc_status': 1,
                                    'radar_list': radar_list,
                                    'voltime': master_voltime,
                                    'trajectory': traj,
                                    'runinfo': infostr})
                        jobs.append(p)
                        p.start()

                    # wait for completion of the jobs
                    for job in jobs:
                        job.join()

                    # add new dataset to radar object if necessary
                    for job in jobs:
                        new_dataset, ind_rad, make_global, jobs_ds = (
                            out_queue.get())
                        result = _add_dataset(
                            new_dataset, radar_list, ind_rad,
                            make_global=make_global)
                        if len(jobs_ds) > 0:
                            jobs_prod.extend(jobs_ds)
                else:
                    for dataset in dataset_levels[level]:
                        new_dataset, ind_rad, jobs_ds = _generate_dataset(
                            dataset, cfg, dscfg[dataset], proc_status=1,
                            radar_list=radar_list, voltime=master_voltime,
                            trajectory=traj, runinfo=infostr)

                        result = _add_dataset(
                            new_dataset, radar_list, ind_rad,
                            make_global=dscfg[dataset]['MAKE_GLOBAL'])
                        if len(jobs_ds) > 0:
                            jobs_prod.extend(jobs_ds)

            # wait until all the products on this time stamp are generated
            for job in jobs_prod:
                job.join()

            # manual garbage collection after processing each radar volume
            gc.collect()

        # if real time processing go on top of the loop and wait for new data
        # if off-line go to post-processing
        if rt:
            last_processed = get_datetime(
                masterfilelist[-1], masterdatatypedescr)
        else:
            end_proc = True

    # only do post processing if program properly terminated by user
    if end_proc:
        # post-processing of the datasets
        print('- Post-processing datasets:')
        for level in sorted(dataset_levels):
            print('-- Process level: '+level)
            if MULTIPROCESSING_DSET:
                jobs = []
                out_queue = mp.Queue()
                for dataset in dataset_levels[level]:
                    p = mp.Process(
                        name=dataset, target=_generate_dataset_mp,
                        args=(dataset, cfg, dscfg[dataset], out_queue),
                        kwargs={'proc_status': 2,
                                'radar_list': None,
                                'voltime': None,
                                'trajectory': traj,
                                'runinfo': infostr})
                    jobs.append(p)
                    p.start()

                # wait for completion of the jobs
                for job in jobs:
                    job.join()
            else:
                for dataset in dataset_levels[level]:
                    new_dataset, ind_rad, jobs_ds = _generate_dataset(
                        dataset, cfg, dscfg[dataset], proc_status=2,
                        radar_list=None, voltime=None, trajectory=traj,
                        runinfo=infostr)

        # manual garbage collection after post-processing
        gc.collect()

    print('- This is the end my friend! See you soon!')


def _user_input_listener(input_queue):
    """
    Permanently listens to the keyword input until the user types "Return"

    Parameters
    ----------
    input_queue : queue object
        the queue object where to put the quit signal

    """
    print("Press Enter to quit: ")
    while True:
        user_input = sys.stdin.read(1)
        if '\n' in user_input or '\r' in user_input:
            warn('Exit requested by user')
            input_queue.put(True)
            break
        time.sleep(1)


def _generate_dataset(dsname, cfg, dscfg, proc_status=0, radar_list=None,
                      voltime=None, trajectory=None, runinfo=None):
    """
    generates a new dataset

    Parameters
    ----------
    dsname : str
        name of the dataset
    cfg : dict
        configuration data
    dscfg : dict
        dataset configuration data
    proc_status : int
        processing status 0: init 1: processing 2: final
    radar_list : list
        a list containing the radar objects
    voltime : datetime
        reference time of the radar(s)
    trajectory : trajectory object
        trajectory object
    runinfo : str
        string containing run info

    Returns
    -------
    Returns
    -------
    new_dataset : dataset object
        The new dataset generated. None otherwise
    ind_rad : int
        the index to the reference radar object

    """
    print('--- Processing dataset: '+dsname)
    try:
        return _process_dataset(
            cfg, dscfg, proc_status=proc_status, radar_list=radar_list,
            voltime=voltime, trajectory=trajectory, runinfo=runinfo)
    except Exception as ee:
        traceback.print_exc()
        return None, None, []


def _generate_dataset_mp(dsname, cfg, dscfg, out_queue, proc_status=0,
                         radar_list=None, voltime=None, trajectory=None,
                         runinfo=None):
    """
    generates a new dataset using multiprocessing

    Parameters
    ----------
    dsname : str
        name of the dataset
    cfg : dict
        configuration data
    dscfg : dict
        dataset configuration data
    out_queue : queue object
        the queue object where to put the output data
    proc_status : int
        processing status 0: init 1: processing 2: final
    radar_list : list
        a list containing the radar objects
    voltime : datetime
        reference time of the radar(s)
    trajectory : trajectory object
        trajectory object
    runinfo : str
        string containing run info

    Returns
    -------
    new_dataset : dataset object
        The new dataset generated. None otherwise
    ind_rad : int
        the index to the reference radar object
    make_global : boolean
        A flag indicating whether the dataset must be made global
    jobs : list
        list of processes used to generate products

    """
    print('--- Processing dataset: '+dsname)
    try:
        new_dataset, ind_rad, jobs = _process_dataset(
            cfg, dscfg, proc_status=proc_status, radar_list=radar_list,
            voltime=voltime, trajectory=trajectory, runinfo=runinfo)
        out_queue.put((new_dataset, ind_rad, dscfg['MAKE_GLOBAL'], jobs))
        out_queue.close()
    except Exception as ee:
        traceback.print_exc()
        out_queue.put((None, None, 0, []))
        out_queue.close()


def _process_dataset(cfg, dscfg, proc_status=0, radar_list=None, voltime=None,
                     trajectory=None, runinfo=None):
    """
    processes a dataset

    Parameters
    ----------
    cfg : dict
        configuration dictionary
    dscfg : dict
        dataset specific configuration dictionary
    proc_status : int
        status of the processing 0: Initialization 1: process of radar volume
        2: Final processing
    radar_list : list
        list of radar objects containing the data to be processed
    voltime : datetime object
        reference time of the radar(s)
    trajectory : Trajectory object
        containing trajectory samples
    runinfo : str
        string containing run info

    Returns
    -------
    new_dataset : dataset object
        The new dataset generated. None otherwise
    ind_rad : int
        the index to the reference radar object
    jobs : list
        a list of processes used to generate products

    """

    dscfg['timeinfo'] = voltime
    try:
        proc_ds_func, dsformat = get_process_func(dscfg['type'],
                                                  dscfg['dsname'])
    except Exception as ee:
        raise

    if (type(proc_ds_func) is str):
        proc_ds_func = getattr(proc, proc_ds_func)

    # Create dataset
    if ('trajectory' in inspect.getfullargspec(proc_ds_func).args):
        new_dataset, ind_rad = proc_ds_func(proc_status, dscfg,
                                            radar_list=radar_list,
                                            trajectory=trajectory)
    else:
        new_dataset, ind_rad = proc_ds_func(proc_status, dscfg,
                                            radar_list=radar_list)

    if new_dataset is None:
        return None, None, []

    try:
        prod_func = get_prodgen_func(dsformat, dscfg['dsname'],
                                     dscfg['type'])
    except Exception as ee:
        raise

    # create the data set products
    jobs = []
    if 'products' in dscfg:
        if MULTIPROCESSING_PROD:
            for product in dscfg['products']:
                p = mp.Process(
                    name=product, target=_generate_prod,
                    args=(new_dataset, cfg, product, prod_func,
                          dscfg['dsname'], voltime),
                    kwargs={'runinfo': runinfo})
                jobs.append(p)
                p.start()

            # wait for completion of the job generation
            # for job in jobs:
            #     job.join()
        else:
            for product in dscfg['products']:
                err = _generate_prod(new_dataset, cfg, product, prod_func,
                                     dscfg['dsname'], voltime, runinfo=runinfo)
    return new_dataset, ind_rad, jobs


def _generate_prod(dataset, cfg, prdname, prdfunc, dsname, voltime,
                   runinfo=None):
    """
    generates a product

    Parameters
    ----------
    dataset : object
        the dataset object
    cfg : dict
        configuration data
    prdname : str
        name of the product
    prdfunc : func
        name of the product processing function
    dsname : str
        name of the dataset
    voltime : datetime object
        reference time of the radar(s)
    runinfo : str
        string containing run info

    Returns
    -------
    cfg : dict
        dictionary containing the configuration data

    """
    print('---- Processing product: ' + prdname)
    prdcfg = _create_prdcfg_dict(cfg, dsname, prdname, voltime,
                                 runinfo=runinfo)
    try:
        result = prdfunc(dataset, prdcfg)
        return 0
    except Exception as ee:
        traceback.print_exc()
        return 1


def _create_cfg_dict(cfgfile):
    """
    creates a configuration dictionary

    Parameters
    ----------
    cfgfile : str
        path of the main config file

    Returns
    -------
    cfg : dict
        dictionary containing the configuration data

    """
    cfg = dict({'configFile': cfgfile})
    try:
        print("- Main config file : %s" % cfgfile)
        cfg = read_config(cfg['configFile'], cfg=cfg)
        print("- Location config file : %s" % cfg['locationConfigFile'])
        cfg = read_config(cfg['locationConfigFile'], cfg=cfg)
        print("- Product config file : %s" % cfg['productConfigFile'])
        cfg = read_config(cfg['productConfigFile'], cfg=cfg)
    except Exception as ee:
        warn(str(ee))
        sys.exit(1)

    # check for mandatory config parameters
    param_must = ['name', 'configpath', 'saveimgbasepath', 'dataSetList']
    for param in param_must:
        if param not in cfg:
            raise Exception("ERROR config: Parameter '%s' undefined!" % param)

    # fill in defaults
    if 'NumRadars' not in cfg:
        cfg.update({'NumRadars': 1})
    if 'TimeTol' not in cfg:
        cfg.update({'TimeTol': 3600.})
    if 'ScanList' not in cfg:
        cfg.update({'ScanList': None})
    else:
        cfg.update({'ScanList': get_scan_list(cfg['ScanList'])})
    if 'datapath' not in cfg:
        cfg.update({'datapath': None})
    if 'path_convention' not in cfg:
        cfg.update({'path_convention': 'MCH'})
    if 'cosmopath' not in cfg:
        cfg.update({'cosmopath': None})
    if 'psrpath' not in cfg:
        cfg.update({'psrpath': None})
    if 'colocgatespath' not in cfg:
        cfg.update({'colocgatespath': None})
    if 'dempath' not in cfg:
        cfg.update({'dempath': None})
    if 'smnpath' not in cfg:
        cfg.update({'smnpath': None})
    if 'disdropath' not in cfg:
        cfg.update({'disdropath': None})
    if 'solarfluxpath' not in cfg:
        cfg.update({'solarfluxpath': None})
    if 'loadbasepath' not in cfg:
        cfg.update({'loadbasepath': None})
    if 'loadname' not in cfg:
        cfg.update({'loadname': None})
    if 'RadarName' not in cfg:
        cfg.update({'RadarName': None})
    if 'RadarRes' not in cfg:
        cfg.update({'RadarRes': None})
    if 'mflossh' not in cfg:
        cfg.update({'mflossh': None})
    if 'mflossv' not in cfg:
        cfg.update({'mflossv': None})
    if 'radconsth' not in cfg:
        cfg.update({'radconsth': None})
    if 'radconstv' not in cfg:
        cfg.update({'radconstv': None})
    if 'lrxh' not in cfg:
        cfg.update({'lrxh': None})
    if 'lrxv' not in cfg:
        cfg.update({'lrxv': None})
    if 'lradomeh' not in cfg:
        cfg.update({'lradomeh': None})
    if 'lradomev' not in cfg:
        cfg.update({'lradomev': None})
    if 'AntennaGain' not in cfg:
        cfg.update({'AntennaGain': None})
    if 'attg' not in cfg:
        cfg.update({'attg': None})
    if 'ScanPeriod' not in cfg:
        warn('WARNING: Scan period not specified. ' +
             'Assumed default value 5 min')
        cfg.update({'ScanPeriod': 5})
    if 'CosmoRunFreq' not in cfg:
        warn('WARNING: COSMO run frequency not specified. ' +
             'Assumed default value 3h')
        cfg.update({'CosmoRunFreq': 3})
    if 'CosmoForecasted' not in cfg:
        warn('WARNING: Hours forecasted by COSMO not specified. ' +
             'Assumed default value 7h (including analysis)')
        cfg.update({'CosmoForecasted': 7})

    # Convert the following strings to string arrays
    strarr_list = ['datapath', 'cosmopath', 'dempath', 'loadbasepath',
                   'loadname', 'RadarName', 'RadarRes', 'ScanList',
                   'imgformat']
    for param in strarr_list:
        if (type(cfg[param]) is str):
            cfg[param] = [cfg[param]]

    return cfg


def _create_datacfg_dict(cfg):
    """
    creates a data configuration dictionary from a config dictionary

    Parameters
    ----------
    cfg : dict
        config dictionary

    Returns
    -------
    datacfg : dict
        data config dictionary

    """

    datacfg = dict({'datapath': cfg['datapath']})
    datacfg.update({'ScanList': cfg['ScanList']})
    datacfg.update({'cosmopath': cfg['cosmopath']})
    datacfg.update({'dempath': cfg['dempath']})
    datacfg.update({'loadbasepath': cfg['loadbasepath']})
    datacfg.update({'loadname': cfg['loadname']})
    datacfg.update({'RadarName': cfg['RadarName']})
    datacfg.update({'RadarRes': cfg['RadarRes']})
    datacfg.update({'ScanPeriod': cfg['ScanPeriod']})
    datacfg.update({'CosmoRunFreq': int(cfg['CosmoRunFreq'])})
    datacfg.update({'CosmoForecasted': int(cfg['CosmoForecasted'])})
    datacfg.update({'path_convention': cfg['path_convention']})

    return datacfg


def _create_dscfg_dict(cfg, dataset, voltime=None):
    """
    creates a dataset configuration dictionary

    Parameters
    ----------
    cfg : dict
        config dictionary
    dataset : str
        name of the dataset
    voltime : datetime object
        time of the dataset

    Returns
    -------
    dscfg : dict
        dataset config dictionary

    """
    dscfg = cfg[dataset]
    dscfg.update({'configpath': cfg['configpath']})
    dscfg.update({'solarfluxpath': cfg['solarfluxpath']})
    dscfg.update({'colocgatespath': cfg['colocgatespath']})
    dscfg.update({'cosmopath': cfg['cosmopath']})
    dscfg.update({'CosmoRunFreq': cfg['CosmoRunFreq']})
    dscfg.update({'CosmoForecasted': cfg['CosmoForecasted']})
    dscfg.update({'RadarName': cfg['RadarName']})
    dscfg.update({'mflossh': cfg['mflossh']})
    dscfg.update({'mflossv': cfg['mflossv']})
    dscfg.update({'radconsth': cfg['radconsth']})
    dscfg.update({'radconstv': cfg['radconstv']})
    dscfg.update({'lrxh': cfg['lrxh']})
    dscfg.update({'lrxv': cfg['lrxv']})
    dscfg.update({'lradomeh': cfg['lradomeh']})
    dscfg.update({'lradomev': cfg['lradomev']})
    dscfg.update({'AntennaGain': cfg['AntennaGain']})
    dscfg.update({'attg': cfg['attg']})
    dscfg.update({'basepath': cfg['saveimgbasepath']})
    dscfg.update({'procname': cfg['name']})
    dscfg.update({'dsname': dataset})
    dscfg.update({'timeinfo': None})
    if ('par_azimuth_antenna' in cfg):
        dscfg.update({'par_azimuth_antenna': cfg['par_azimuth_antenna']})
    if ('par_elevation_antenna' in cfg):
        dscfg.update({'par_elevation_antenna': cfg['par_elevation_antenna']})
    if ('asr_highbeam_antenna' in cfg):
        dscfg.update({'asr_highbeam_antenna': cfg['asr_highbeam_antenna']})
    if ('asr_lowbeam_antenna' in cfg):
        dscfg.update({'asr_lowbeam_antenna': cfg['asr_lowbeam_antenna']})
    if ('asr_position' in cfg):
        dscfg.update({'asr_position': cfg['asr_position']})

    # indicates the dataset has been initialized and aux data is available
    dscfg.update({'initialized': False})
    dscfg.update({'global_data': None})

    if 'MAKE_GLOBAL' not in dscfg:
        dscfg.update({'MAKE_GLOBAL': 0})

    # Convert the following strings to string arrays
    strarr_list = ['datatype']
    for param in strarr_list:
        if param in dscfg:
            if (type(dscfg[param]) is str):
                dscfg[param] = [dscfg[param]]

    return dscfg


def _create_prdcfg_dict(cfg, dataset, product, voltime, runinfo=None):
    """
    creates a product configuration dictionary

    Parameters
    ----------
    cfg : dict
        config dictionary
    dataset : str
        name of the dataset used to create the product
    product : str
        name of the product
    voltime : datetime object
        time of the dataset

    Returns
    -------
    prdcfg : dict
        product config dictionary

    """

    # Ugly copying of dataset config parameters to product
    # config dict. Better: Make dataset config dict available to
    # the product generation.
    prdcfg = cfg[dataset]['products'][product]
    prdcfg.update({'procname': cfg['name']})
    prdcfg.update({'basepath': cfg['saveimgbasepath']})
    prdcfg.update({'smnpath': cfg['smnpath']})
    prdcfg.update({'disdropath': cfg['disdropath']})
    prdcfg.update({'cosmopath': cfg['cosmopath']})
    prdcfg.update({'ScanPeriod': cfg['ScanPeriod']})
    prdcfg.update({'imgformat': cfg['imgformat']})
    if 'ppiImageConfig' in cfg:
        prdcfg.update({'ppiImageConfig': cfg['ppiImageConfig']})
    if 'rhiImageConfig' in cfg:
        prdcfg.update({'rhiImageConfig': cfg['rhiImageConfig']})
    if 'sunhitsImageConfig' in cfg:
        prdcfg.update({'sunhitsImageConfig': cfg['sunhitsImageConfig']})
    prdcfg.update({'dsname': dataset})
    prdcfg.update({'dstype': cfg[dataset]['type']})
    prdcfg.update({'prdname': product})
    prdcfg.update({'timeinfo': voltime})
    prdcfg.update({'runinfo': runinfo})
    if 'dssavename' in cfg[dataset]:
        prdcfg.update({'dssavename': cfg[dataset]['dssavename']})

    return prdcfg


def _get_datatype_list(cfg, radarnr='RADAR001'):
    """
    get list of unique input data types

    Parameters
    ----------
    cfg : dict
        config dictionary
    radarnr : str
        radar number identifier

    Returns
    -------
    datatypesdescr : list
        list of data type descriptors

    """
    datatypesdescr = set()

    for datasetdescr in cfg['dataSetList']:
        proclevel, dataset = get_dataset_fields(datasetdescr)
        if 'datatype' in cfg[dataset]:
            if isinstance(cfg[dataset]['datatype'], str):
                (radarnr_descr, datagroup, datatype_aux, dataset_save,
                 product_save) = (
                    get_datatype_fields(cfg[dataset]['datatype']))
                if datagroup != 'PROC' and radarnr_descr == radarnr:
                    if ((dataset_save is None) and (product_save is None)):
                        datatypesdescr.add(
                            radarnr_descr+":"+datagroup+":"+datatype_aux)
                    else:
                        datatypesdescr.add(
                            radarnr_descr+":"+datagroup+":"+datatype_aux+"," +
                            dataset_save+","+product_save)
            else:
                for datatype in cfg[dataset]['datatype']:
                    (radarnr_descr, datagroup, datatype_aux, dataset_save,
                     product_save) = (
                        get_datatype_fields(datatype))
                    if datagroup != 'PROC' and radarnr_descr == radarnr:
                        if ((dataset_save is None) and (product_save is None)):
                            datatypesdescr.add(
                                radarnr_descr+":"+datagroup+":"+datatype_aux)
                        else:
                            datatypesdescr.add(
                                radarnr_descr+":"+datagroup+":"+datatype_aux +
                                ","+dataset_save+","+product_save)

    datatypesdescr = list(datatypesdescr)

    return datatypesdescr


def _get_datasets_list(cfg):
    """
    get list of dataset at each processing level

    Parameters
    ----------
    cfg : dict
        config dictionary

    Returns
    -------
    dataset_levels : dict
        a dictionary containing the list of datasets at each processing level

    """
    dataset_levels = dict({'l0': list()})
    for datasetdescr in cfg['dataSetList']:
        proclevel, dataset = get_dataset_fields(datasetdescr)
        if proclevel in dataset_levels:
            dataset_levels[proclevel].append(dataset)
        else:
            dataset_levels.update({proclevel: [dataset]})

    return dataset_levels


def _get_masterfile_list(datatypesdescr, starttime, endtime, datacfg,
                         scan_list=None):
    """
    get master file list

    Parameters
    ----------
    datatypesdescr : list
        list of unique data type descriptors
    starttime, endtime : datetime object
        start and end of processing period
    datacfg : dict
        data configuration dictionary
    scan_list : list
        list of scans

    Returns
    -------
    masterfilelist : list
        the list of master files
    masterdatatypedescr : str
        the master data type descriptor

    """
    masterdatatypedescr = None
    masterscan = None
    for datatypedescr in datatypesdescr:
        radarnr, datagroup, datatype, dataset, product = get_datatype_fields(
            datatypedescr)
        if ((datagroup != 'COSMO') and (datagroup != 'RAD4ALPCOSMO') and
                (datagroup != 'DEM') and (datagroup != 'RAD4ALPDEM')):
            masterdatatypedescr = datatypedescr
            if scan_list is not None:
                masterscan = scan_list[int(radarnr[5:8])-1][0]
            break

    # if data type is not radar use dBZ as reference
    if masterdatatypedescr is None:
        for datatypedescr in datatypesdescr:
            radarnr, datagroup, datatype, dataset, product = (
                get_datatype_fields(datatypedescr))
            if datagroup == 'COSMO':
                masterdatatypedescr = radarnr+':RAINBOW:dBZ'
                if scan_list is not None:
                    masterscan = scan_list[int(radarnr[5:8])-1][0]
                break
            elif datagroup == 'RAD4ALPCOSMO':
                masterdatatypedescr = radarnr+':RAD4ALP:dBZ'
                if scan_list is not None:
                    masterscan = scan_list[int(radarnr[5:8])-1][0]
                break
            elif datagroup == 'DEM':
                masterdatatypedescr = radarnr+':RAINBOW:dBZ'
                if scan_list is not None:
                    masterscan = scan_list[int(radarnr[5:8])-1][0]
                break
            elif datagroup == 'RAD4ALPDEM':
                masterdatatypedescr = radarnr+':RAD4ALP:dBZ'
                if scan_list is not None:
                    masterscan = scan_list[int(radarnr[5:8])-1][0]
                break

    masterfilelist = get_file_list(
        masterdatatypedescr, starttime, endtime, datacfg,
        scan=masterscan)

    return masterfilelist, masterdatatypedescr, masterscan


def _add_dataset(new_dataset, radar_list, ind_rad, make_global=True):
    """
    adds a new field to an existing radar object

    Parameters
    ----------
    new_dataset : radar object
        the radar object containing the new fields
    radar : radar object
        the radar object containing the global data
    make_global : boolean
        if true a new field is added to the global data

    Returns
    -------
    0 if successful. None otherwise

    """
    if radar_list is None:
        return None

    if not make_global:
        return None

    if new_dataset is None:
        return None

    for field in new_dataset.fields:
        print('Adding field: '+field)
        radar_list[ind_rad].add_field(
            field, new_dataset.fields[field],
            replace_existing=True)
    return 0


def _warning_format(message, category, filename, lineno, file=None, line=None):
    return '%s (%s:%s)\n' % (message, filename, lineno)
