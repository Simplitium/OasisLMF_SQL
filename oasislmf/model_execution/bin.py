#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Python utilities used for setting up the resources needed to complete a
    model run, i.e. generating ktools outputs from Oasis files.
"""

from __future__ import print_function

import glob
import logging
import re
import shutilwhich
import tarfile

from itertools import chain
from future.utils import (
    viewkeys,
    viewvalues,
)

from pathlib2 import Path

__all__ = [
    'create_binary_files',
    'prepare_model_run_directory',
    'prepare_model_run_inputs'
]

import os
import shutil
import subprocess

from ..utils.exceptions import OasisException
from .files import TAR_FILE, INPUT_FILES, GUL_INPUT_FILES, IL_INPUT_FILES


def prepare_model_run_directory(
    run_dir_path,
    oasis_files_src_path=None,
    ri=False,
    analysis_settings_json_src_file_path=None,
    model_data_src_path=None,
    inputs_archive=None,
):
    """
    Ensures that the model run directory has the correct folder structure in
    order for the model run script (ktools) to be executed. Without the RI
    flag the model run directory will have the following structure

    ::

        <run_directory>
        ├── fifo/
        ├── input/
        │   └── csv/
        ├── output/
        ├── static/
        └── work/
        ├── analysis_settings.json
        └── run_ktools.sh


    where the direct GUL and/or FM input files exist in the ``input/csv``
    subfolder and the corresponding binaries exist in the ``input`` subfolder.

    With the RI flag the model run directory has the following structure

    ::

        <run_directory>
        ├── fifo
        ├── input
        ├── RI_1
        ├── RI_2
        ├── ...
        ├── output
        ├── static
        └── work
        └── ri_layers.json
        ├── analysis_settings.json
        └── run_ktools.sh

    where the direct GUL and/or FM input files, and the corresponding binaries
    exist in the ``input`` subfolder, and the RI layer input files and binaries
    exist in the ``RI`` prefixed subfolders.

    If any subfolders are missing they are created.

    Optionally, if the path to a set of Oasis files is provided then they
    are copied into the ``input/csv`` subfolder.

    Optionally, if the path to the analysis settings JSON file is provided
    then it is copied to the base of the run directory.

    Optionally, if the path to model data is provided then the files are
    symlinked into the ``static`` subfolder provided the OS is of type
    Darwin or Linux, otherwise the source folder tree is recursively
    copied into the ``static`` subfolder.

    :param run_directory: the model run directory
    :type run_directory: str

    :param oasis_files_src_path: path to a set of Oasis files
    :type oasis_files_src_path: str

    :param ri: Boolean flag for RI mode
    :type ri: bool

    :param analysis_settings_json_src_file_path: analysis settings JSON file path
    :type analysis_settings_json_src_file_path: str

    :param model_data_src_path: model data source path
    :type model_data_src_path: str

    :param inputs_archive: path to a tar file containing input files
    :type inputs_archive: str
    """
    #import ipdb; ipdb.set_trace()
    try:
        for subdir in ['fifo', 'output', 'static', 'work']:
            Path(run_dir_path, subdir).mkdir(parents=True, exist_ok=True)

        if not inputs_archive:
            Path(run_dir_path, 'input', 'csv').mkdir(parents=True, exist_ok=True) if not ri else Path(run_dir_path, 'input').mkdir(parents=True, exist_ok=True)
        else:
            with tarfile.open(inputs_archive) as input_tarfile:
                p = os.path.join(run_dir_path, 'input') 
                input_tarfile.extractall(path=p)
                
                for ri_dir in [d for d in os.listdir(p) if 'RI_' in d]:
                    shutil.move(os.path.join(p, ri_dir), run_dir_path)


        oasis_files_destpath = os.path.join(run_dir_path, 'input', 'csv') if not ri else os.path.join(run_dir_path, 'input')

        if oasis_files_src_path and oasis_files_src_path != oasis_files_destpath:
            for p in os.listdir(oasis_files_src_path):
                src_fp = os.path.join(oasis_files_src_path, p)
                if not (re.match(r'RI_\d+$', p) or p == 'ri_layers.json'):
                    shutil.copy2(src_fp, oasis_files_destpath)
                else:
                    copy_func = shutil.copytree if re.match(r'RI_\d+$', p) else shutil.copy2
                    copy_func(src_fp, os.path.join(run_dir_path, p))

        if analysis_settings_json_src_file_path:
            analysis_settings_json_dest_file_path = os.path.join(run_dir_path, 'analysis_settings.json')
            shutil.copyfile(analysis_settings_json_src_file_path, analysis_settings_json_dest_file_path)

        if model_data_src_path:
            model_data_dest_path = os.path.join(run_dir_path, 'static')

            for path in glob.glob(os.path.join(model_data_src_path, '*')):
                filename = os.path.basename(path)
                try:
                    os.symlink(path, os.path.join(model_data_dest_path, filename))
                except Exception:
                    shutil.copytree(model_data_src_path, os.path.join(model_data_dest_path, filename))

    except OSError as e:
        raise OasisException(e)


def _prepare_input_bin(run_dir, bin_name, model_settings, setting_key=None, ri=False):
    bin_fp = os.path.join(run_dir, 'input', '{}.bin'.format(bin_name))
    if not os.path.exists(bin_fp):
        setting_val = model_settings.get(setting_key)

        if not setting_val:
            model_data_bin_fp = os.path.join(run_dir, 'static', '{}.bin'.format(bin_name))
        else:
            # Format for data file names
            setting_val = setting_val.replace(' ', '_').lower()
            model_data_bin_fp = os.path.join(run_dir, 'static', '{}_{}.bin'.format(bin_name, setting_val))

        if not os.path.exists(model_data_bin_fp):
            raise OasisException('Could not find {} data file: {}'.format(bin_name, model_data_bin_fp))

        shutil.copyfile(model_data_bin_fp, bin_fp)


def prepare_model_run_inputs(analysis_settings, run_dir, ri=False):
    """
    Sets up binary files in the model inputs directory.

    :param analysis_settings: model analysis settings dict
    :type analysis_settings: dict

    :param run_dir: model run directory
    :type run_dir: str
    """
    try:
        model_settings = analysis_settings.get('model_settings', {})

        _prepare_input_bin(run_dir, 'events', model_settings, setting_key='event_set', ri=ri)
        _prepare_input_bin(run_dir, 'returnperiods', model_settings, ri=ri)
        _prepare_input_bin(run_dir, 'occurrence', model_settings, setting_key='event_occurrence_id', ri=ri)

        if os.path.exists(os.path.join(run_dir, 'static', 'periods.bin')):
            _prepare_input_bin(run_dir, 'periods', model_settings, ri=ri)
    except (OSError, IOError) as e:
        raise OasisException(e)


def check_inputs_directory(directory_to_check, do_il=False, do_ri=False, check_binaries=True):
    """
    Check that all the required files are present in the directory.

    :param directory_to_check: directory containing the CSV files
    :type directory_to_check: string

    :param do_il: check insuured loss files
    :type do_il: bool

    :param do_il: check resinsurance sub-folders
    :type do_il: bool

    :param check_binaries: check binary files are not present
    :type check_binaries: bool
    """
    # Check the top level directory, that containes the core files and any direct FM files
    _check_each_inputs_directory(directory_to_check, do_il=do_il, check_binaries=check_binaries)

    if do_ri:
        for ri_directory_to_check in glob.glob('{}{}RI_\d+$'.format(directory_to_check, os.path.sep)):
            _check_each_inputs_directory(ri_directory_to_check, do_il=True, check_binaries=check_binaries)


def _check_each_inputs_directory(directory_to_check, do_il=False, check_binaries=True):
    """
    Detailed check of a specific directory
    """

    if do_il:
        input_files = (f['name'] for f in viewvalues(INPUT_FILES) if f['type'] != 'optional')
    else:
        input_files = (f['name'] for f in viewvalues(INPUT_FILES) if f['type'] not in ['optional', 'il'])

    for input_file in input_files:
        file_path = os.path.join(directory_to_check, input_file + ".csv")
        if not os.path.exists(file_path):
            raise OasisException("Failed to find {}".format(file_path))

        if check_binaries:
            file_path = os.path.join(directory_to_check, input_file + ".bin")
            if os.path.exists(file_path):
                raise OasisException("Binary file already exists: {}".format(file_path))


def create_binary_files(csv_directory, bin_directory, do_il=False, do_ri=False):
    """
    Create the binary files.

    :param csv_directory: the directory containing the CSV files
    :type csv_directory: str

    :param bin_directory: the directory to write the binary files
    :type bin_directory: str

    :param do_il: whether to create the binaries required for insured loss calculations
    :type do_il: bool

    :param do_ri: whether to create the binaries required for reinsurance calculations
    :type do_ri: bool

    :raises OasisException: If one of the conversions fails
    """
    csvdir = os.path.abspath(csv_directory)
    bindir = os.path.abspath(bin_directory)

    do_il = do_il or do_ri

    _create_set_of_binary_files(csvdir, bindir, do_il)

    if do_ri:
        for ri_csvdir in glob.glob('{}{}RI_[0-9]*'.format(csvdir, os.sep)):
            _create_set_of_binary_files(
                ri_csvdir, os.path.join(bindir, os.path.basename(ri_csvdir)), do_il=True)

def _create_set_of_binary_files(csv_directory, bin_directory, do_il=False):
    """
    Create a set of binary files.
    """
    if not os.path.exists(bin_directory):
        os.mkdir(bin_directory)

    if do_il:
        input_files = viewvalues(INPUT_FILES)
    else:
        input_files = (f for f in viewvalues(INPUT_FILES) if f['type'] != 'il')

    for input_file in input_files:
        conversion_tool = input_file['conversion_tool']
        input_file_path = os.path.join(csv_directory, '{}.csv'.format(input_file['name']))
        if not os.path.exists(input_file_path):
            continue

        output_file_path = os.path.join(bin_directory, '{}.bin'.format(input_file['name']))
        cmd_str = "{} < {} > {}".format(conversion_tool, input_file_path, output_file_path)

        try:
            subprocess.check_call(cmd_str, stderr=subprocess.STDOUT, shell=True)
        except subprocess.CalledProcessError as e:
            raise OasisException(e)

def check_binary_tar_file(tar_file_path, check_il=False):
    """
    Checks that all required files are present

    :param tar_file_path: Path to the tar file to check
    :type tar_file_path: str

    :param check_il: Flag whether to check insured loss files
    :type check_il: bool

    :raises OasisException: If a required file is missing

    :return: True if all required files are present, False otherwise
    :rtype: bool
    """
    expected_members = ('{}.bin'.format(f['name']) for f in viewvalues(GUL_INPUT_FILES))

    if check_il:
        expected_members = chain(expected_members, ('{}.bin'.format(f['name']) for f in viewvalues(IL_INPUT_FILES)))

    with tarfile.open(tar_file_path) as tar:
        for member in expected_members:
            try:
                tar.getmember(member)
            except KeyError:
                raise OasisException('{} is missing from the tar file {}.'.format(member, tar_file_path))

    return True


def create_binary_tar_file(directory):
    """
    Package the binaries in a gzipped tar.
    
    :param directory: Path containing the binaries
    :type tar_file_path: str    
    """
    with tarfile.open(
        os.path.join(directory, TAR_FILE),"w:gz") as tar:

        for f in glob.glob('{}*{}*.bin'.format(directory, os.sep)):
            logging.info("Adding {} {}".format(f, os.path.relpath(f, directory)))
            relpath = os.path.relpath(f, directory)
            tar.add(f, arcname=relpath)

        for f in glob.glob('{}*{}*{}*.bin'.format(directory, os.sep, os.sep)):
            relpath = os.path.relpath(f, directory)
            tar.add(f, arcname=relpath)


def check_conversion_tools(do_il=False):
    """
    Check that the conversion tools are available
    
    :param do_il: Flag whether to check insured loss tools
    :type do_il: bool

    :return: True if all required tools are present, False otherwise
    :rtype: bool  
    """
    if do_il:
        input_files = viewvalues(INPUT_FILES)
    else:
        input_files = (f for f in viewvalues(INPUT_FILES) if f['type'] != 'il')

    for input_file in input_files:
        tool = input_file['conversion_tool']
        if shutilwhich.which(tool) is None:
            error_message = "Failed to find conversion tool: {}".format(tool)
            logging.error(error_message)
            raise OasisException(error_message)

    return True


def cleanup_bin_directory(directory):
    """
    Clean the tar and binary files.
    """
    for file in chain([TAR_FILE], (f + '.bin' for f in viewkeys(INPUT_FILES))):
        file_path = os.path.join(directory, file)
        if os.path.exists(file_path):
            os.remove(file_path)
