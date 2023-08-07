"""
==================================
Input and output (:mod:`pyrad.io`)
==================================

.. currentmodule:: pyrad.io

Functions to read and write data and configuration files.

Reading configuration files
===========================

.. autosummary::
    :toctree: generated/

    read_config

Reading radar data
==================

.. autosummary::
    :toctree: generated/

    get_data

Reading cosmo data
==================

.. autosummary::
    :toctree: generated/

    cosmo2radar_data
    cosmo2radar_coord
    hzt2radar_data
    hzt2radar_coord
    get_cosmo_fields
    get_iso0_field
    read_cosmo_data
    read_cosmo_coord
    read_hzt_data
    read_iso0_mf_data
    read_iso0_grib_data
    iso2radar_data
    grib2radar_data
    get_iso0_ref

Reading DEM data
==================

.. autosummary::
    :toctree: generated/

    dem2radar_data
    dem2radar_coord
    read_idrisi_data
    read_idrisi_metadata

Reading other data
==================

.. autosummary::
    :toctree: generated/

    read_centroids_npz
    read_centroids
    read_proc_periods
    read_last_state
    read_status
    read_rad4alp_cosmo
    read_rad4alp_vis
    read_excess_gates
    read_colocated_gates
    read_colocated_data
    read_timeseries
    read_ts_cum
    read_monitoring_ts
    read_intercomp_scores_ts
    get_sensor_data
    read_smn
    read_smn2
    read_coord_sensors
    read_disdro_scattering
    read_sun_hits
    read_sun_hits_multiple_days
    read_sun_retrieval
    read_solar_flux
    read_selfconsistency
    read_antenna_pattern
    read_meteorage
    read_lightning
    read_lightning_traj
    read_lightning_all
    read_trt_scores
    read_trt_data
    read_trt_traj_data
    read_trt_thundertracking_traj_data
    read_trt_cell_lightning
    read_trt_info_all
    read_trt_info_all2
    read_trt_info
    read_trt_info2
    read_thundertracking_info
    read_rhi_profile
    read_vpr_theo_parameters
    read_histogram
    read_quantiles
    read_profile_ts
    read_histogram_ts
    read_quantiles_ts
    read_ml_ts
    read_windmills_data
    read_windcube

Writing data
==================

.. autosummary::
    :toctree: generated/

    write_vol_csv
    write_vol_kml
    write_centroids
    write_proc_periods
    write_ts_lightning
    send_msg
    write_alarm_msg
    write_last_state
    write_smn
    write_trt_info
    write_trt_thundertracking_data
    write_trt_cell_data
    write_trt_cell_scores
    write_trt_cell_lightning
    write_trt_rpc
    write_vpr_theo_params
    write_vpr_info
    write_rhi_profile
    write_field_coverage
    write_cdf
    write_histogram
    write_quantiles
    write_multiple_points
    write_multiple_points_grid
    write_ts_polar_data
    write_ts_grid_data
    write_ts_cum
    write_ts_stats
    write_monitoring_ts
    write_excess_gates
    write_intercomp_scores_ts
    write_colocated_gates
    write_colocated_data
    write_colocated_data_time_avg
    write_sun_hits
    write_sun_retrieval
    write_fixed_angle


Auxiliary functions
===================

.. autosummary::
    :toctree: generated/

    get_rad4alp_prod_fname
    map_hydro
    map_Doppler
    get_save_dir
    make_filename
    generate_field_name_str
    get_fieldname_pyart
    get_fieldname_cosmo
    get_field_unit
    get_file_list
    get_rad4alp_dir
    get_rad4alp_grid_dir
    get_trtfile_list
    get_new_rainbow_file_name
    get_datatype_fields
    get_dataset_fields
    get_datetime
    find_raw_cosmo_file
    find_hzt_file
    find_iso0_file
    find_iso0_grib_file
    find_date_in_file_name
    _get_datetime

Trajectory
==========

.. autosummary::
    :toctree: generated/

    Trajectory

TimeSeries
==========

.. autosummary::
    :toctree: generated/

    TimeSeries

"""














__all__ = [s for s in dir() if not s.startswith('_')]
