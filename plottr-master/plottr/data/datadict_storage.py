"""plottr.data.datadict_storage

Provides file-storage tools for the DataDict class.

Description of the HDF5 storage format
======================================

We use a simple mapping from DataDict to the HDF5 file. Within the file,
a single DataDict is stored in a (top-level) group of the file.
The data fields are datasets within that group.

Global meta data of the DataDict are attributes of the group; field meta data
are attributes of the dataset (incl., the `unit` and `axes` values). The meta
data keys are given exactly like in the DataDict, i.e., incl the double
underscore pre- and suffix.
"""
import os
import time
from enum import Enum
from typing import Any, Union, Optional, List

import numpy as np
import h5py

from plottr import QtGui, Signal, Slot

from ..node import (
    Node, NodeWidget, updateOption, updateGuiFromNode,
    emitGuiUpdate,
)

from .datadict import DataDict, is_meta_key

__author__ = 'Wolfgang Pfaff'
__license__ = 'MIT'

DATAFILEXT = '.ddh5'
TIMESTRFORMAT = "%Y-%m-%d %H:%M:%S"


class AppendMode(Enum):
    """How/Whether to append data to existing data."""
    #: data that is additional compared to already existing data is appended
    new = 0
    #: all data is appended to existing data
    all = 1
    #: data is overwritten
    none = 2


def h5ify(obj: Any) -> Any:
    """
    Convert an object into something that we can assing to an HDF5 attribute.

    Performs the following conversions:
    - list/array of strings -> numpy chararray of unicode type

    :param obj: input object
    :return: object, converted if necessary
    """
    if isinstance(obj, list):
        all_string = True
        for elt in obj:
            if not isinstance(elt, str):
                all_string = False
                break
        if not all_string:
            obj = np.array(obj)

    if type(obj) == np.ndarray and obj.dtype.kind == 'U':
        return np.chararray.encode(obj, encoding='utf8')

    return obj


def deh5ify(obj: Any) -> Any:
    """Convert slightly mangled types back to more handy ones."""
    if type(obj) == bytes:
        return obj.decode()

    if type(obj) == np.ndarray and obj.dtype.kind == 'S':
        return np.chararray.decode(obj)

    return obj


def set_attr(h5obj: Any, name: str, val: Any):
    """Set attribute `name` of object `h5obj` to `val`

    Use :func:`h5ify` to convert the object, then try to set the attribute
    to the returned value. If that does not succeed due to a HDF5 typing
    restriction, set the attribute to the string representation of the value.
    """
    try:
        h5obj.attrs[name] = h5ify(val)
    except TypeError:
        newval = str(val)
        h5obj.attrs[name] = h5ify(newval)


def add_cur_time_attr(h5obj: Any, name: str = 'creation',
                      prefix: str = '__', suffix: str = '__'):
    """Add current time information to the given HDF5 object."""

    t = time.localtime()
    tsec = time.mktime(t)
    tstr = time.strftime(TIMESTRFORMAT, t)

    set_attr(h5obj, prefix + name + '_time_sec' + suffix, tsec)
    set_attr(h5obj, prefix + name + '_time_str' + suffix, tstr)


def init_path(filepath: str):
    """Init a new file.

    create the folder structure, if necessary, and the file.

    :param filepath: full file path
    """
    folder, path = os.path.split(filepath)
    if not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)

    # if not os.path.exists(filepath):
    #     with h5py.File(filepath, 'w', libver='latest') as _:
    #         pass


def datadict_to_hdf5(datadict: DataDict,
                     basepath: str = None,
                     groupname: str = 'data',
                     append_mode: AppendMode = AppendMode.new,
                     swmr_mode: bool = True):
    """Write a DataDict to DDH5

    Note: meta data is only written during initial writing of the dataset.
    If we're appending to existing datasets, we're not setting meta
    data anymore.

    :param datadict: datadict to write to disk.
    :param basepath: path of the file, without extension.
    :param groupname: name of the top level group to store the data in
    :param append_mode:
        - `AppendMode.none` : delete and re-create group
        - `AppendMode.new` : append rows in the datadict that exceed
            the number of existing rows in the dataset already stored.
            Note: we're not checking for content, only length!
        - `AppendMode.all` : append all data in datadict to file data sets
    :param swmr_mode: use HDF5 SWMR mode on the file when appending.
    """

    if len(basepath) > len(DATAFILEXT) and \
            basepath[-len(DATAFILEXT):] == DATAFILEXT:
        filepath = basepath
    else:
        filepath = basepath + DATAFILEXT

    if not os.path.exists(filepath):
        init_path(filepath)

    with h5py.File(filepath, mode='a', libver='latest') as f:
        if append_mode is AppendMode.none:
            init_file(f, groupname)
        write_data_to_file(datadict, f, groupname, append_mode, swmr_mode)


def init_file(f: h5py.File,
              groupname: str = 'data'):

    if groupname in f:
        del f[groupname]
        f.flush()
        grp = f.create_group(groupname)
        add_cur_time_attr(grp)
        f.flush()
    else:
        grp = f.create_group(groupname)
        add_cur_time_attr(grp)
        f.flush()


def write_data_to_file(datadict: DataDict,
                       f: h5py.File,
                       groupname: str = 'data',
                       append_mode: AppendMode = AppendMode.new,
                       swmr_mode: bool = True):

    if groupname not in f:
        raise RuntimeError('Group does not exist, initialize file first.')
    grp = f[groupname]

    # if we want to use swmr, we need to make sure that we're not
    # creating any more objects (see hdf5 docs).
    allexist = True
    for k, v in datadict.data_items():
        if k not in grp:
            allexist = False

    # add top-level meta data.
    for k, v in datadict.meta_items(clean_keys=False):
        set_attr(grp, k, v)

    f.flush()
    if allexist and swmr_mode and not f.swmr_mode:
        f.swmr_mode = True

    for k, v in datadict.data_items():
        data = v['values']
        shp = data.shape
        nrows = shp[0]

        # create new dataset, add axes and unit metadata
        if k not in grp:
            maxshp = tuple([None] + list(shp[1:]))
            ds = grp.create_dataset(k, maxshape=maxshp, data=data)

            # add meta data
            add_cur_time_attr(ds)

            if v.get('axes', []) != []:
                set_attr(ds, 'axes', v['axes'])
            if v.get('unit', "") != "":
                set_attr(ds, 'unit', v['unit'])

            for kk, vv in datadict.meta_items(k, clean_keys=False):
                set_attr(ds, kk, vv)

            ds.flush()

        # if the dataset already exits, append data according to
        # chosen append mode.
        else:
            ds = grp[k]
            dslen = ds.shape[0]

            if append_mode == AppendMode.new:
                newshp = tuple([nrows] + list(shp[1:]))
                ds.resize(newshp)
                ds[dslen:] = data[dslen:]
            elif append_mode == AppendMode.all:
                newshp = tuple([dslen + nrows] + list(shp[1:]))
                ds.resize(newshp)
                ds[dslen:] = data[:]

            ds.flush()
    f.flush()


def file_is_readable(filepath: str,
                     swmr_mode=True,
                     n_retries: int = 5,
                     retry_delay: float = 0.01) -> bool:

    cur_try = 0
    while True:
        try:
            with h5py.File(filepath, mode='r',
                           libver='latest', swmr=swmr_mode) as f:
                pass
            return True
        except OSError:
            cur_try += 1
            if cur_try <= n_retries:
                time.sleep(retry_delay)
                cur_try += 1
            else:
                raise


def datadict_from_hdf5(basepath: str,
                       groupname: str = 'data',
                       startidx: Union[int, None] = None,
                       stopidx: Union[int, None] = None,
                       structure_only: bool = False,
                       ignore_unequal_lengths: bool = True,
                       swmr_mode: bool = True,
                       n_retries: int = 5,
                       retry_delay: float = 0.01) -> DataDict:
    """Load a DataDict from file.

    :param basepath: full filepath without the file extension
    :param groupname: name of hdf5 group
    :param startidx: start row
    :param stopidx: end row + 1
    :param structure_only: if `True`, don't load the data values
    :param ignore_unequal_lengths: if `True`, don't fail when the rows have
        unequal length; will return the longest consistent DataDict possible.
    :param swmr_mode: if `True`, open HDF5 file in SWMR mode.
    :return: validated DataDict.
    """

    if len(basepath) > len(DATAFILEXT) and \
            basepath[-len(DATAFILEXT):] == DATAFILEXT:
        filepath = basepath
    else:
        filepath = basepath + DATAFILEXT

    if not os.path.exists(filepath):
        raise ValueError("Specified file does not exist.")

    if startidx is None:
        startidx = 0

    if file_is_readable(filepath, swmr_mode=swmr_mode,
                        n_retries=n_retries, retry_delay=retry_delay):
        pass

    res = {}
    with h5py.File(filepath, 'r', libver='latest', swmr=swmr_mode) as f:
        if groupname not in f:
            raise ValueError('Group does not exist.')

        grp = f[groupname]
        keys = list(grp.keys())
        lens = [len(grp[k][:]) for k in keys]

        if len(set(lens)) > 1:
            if not ignore_unequal_lengths:
                raise RuntimeError('Unequal lengths in the datasets.')

            if stopidx is None or stopidx > min(lens):
                stopidx = min(lens)
        else:
            if stopidx is None or stopidx > lens[0]:
                stopidx = lens[0]

        for attr in grp.attrs:
            if is_meta_key(attr):
                res[attr] = deh5ify(grp.attrs[attr])

        for k in keys:
            ds = grp[k]
            entry = dict(values=np.array([]), )

            if 'axes' in ds.attrs:
                entry['axes'] = deh5ify(ds.attrs['axes']).tolist()
            else:
                entry['axes'] = []

            if 'unit' in ds.attrs:
                entry['unit'] = deh5ify(ds.attrs['unit'])

            if not structure_only:
                entry['values'] = ds[startidx:stopidx]

            entry['__shape__'] = ds[:].shape

            # and now the meta data
            for attr in ds.attrs:
                if is_meta_key(attr):
                    _val = deh5ify(ds.attrs[attr])
                    entry[attr] = deh5ify(ds.attrs[attr])

            res[k] = entry

    dd = DataDict(**res)
    dd.validate()
    return dd


def all_datadicts_from_hdf5(basepath: str, *args, **kwargs):
    if len(basepath) > len(DATAFILEXT) and \
            basepath[-len(DATAFILEXT):] == DATAFILEXT:
        filepath = basepath
    else:
        filepath = basepath + DATAFILEXT

    if not os.path.exists(filepath):
        raise ValueError("Specified file does not exist.")

    ret = {}
    if file_is_readable(filepath, swmr_mode=kwargs.get('swmr_mode', True)):
        with h5py.File(filepath, mode='r', libver='latest',
                       swmr=kwargs.get('swmr_mode', True)) as f:
            keys = [k for k in f.keys()]

        for k in keys:
            ret[k] = datadict_from_hdf5(basepath, groupname=k, *args, **kwargs)

    return ret


# Node for monitoring #

class DDH5LoaderWidget(NodeWidget):

    def __init__(self, node: Node = None):
        super().__init__(node=node)

        self.fileinput = QtGui.QLineEdit()
        self.groupinput = QtGui.QLineEdit('data')
        self.reload = QtGui.QPushButton('Reload')

        self.optSetters = {
            'filepath': self.fileinput.setText,
            'groupname': self.groupinput.setText,
        }
        self.optGetters = {
            'filepath': self.fileinput.text,
            'groupname': self.groupinput.text,
        }

        flayout = QtGui.QFormLayout()
        flayout.addRow('File path:', self.fileinput)
        flayout.addRow('Group:', self.groupinput)

        vlayout = QtGui.QVBoxLayout()
        vlayout.addLayout(flayout)
        vlayout.addWidget(self.reload)

        self.setLayout(vlayout)

        self.fileinput.textEdited.connect(
            lambda x: self.signalOption('filepath')
        )
        self.groupinput.textEdited.connect(
            lambda x: self.signalOption('groupname')
        )
        self.reload.pressed.connect(self.node.update)


class DDH5Loader(Node):
    nodeName = 'DDH5Loader'
    uiClass = DDH5LoaderWidget
    useUi = True
    nRetries = 5
    retryDelay = 0.01

    def __init__(self, name: str):
        self._filepath = None
        self._groupname = None

        super().__init__(name)

        self.groupname = 'data'
        self.nLoadedRecords = 0

    @property
    def filepath(self):
        return self._filepath

    @filepath.setter
    @updateOption('filepath')
    def filepath(self, val):
        self._filepath = val

    @property
    def groupname(self):
        return self._groupname

    @groupname.setter
    @updateOption('groupname')
    def groupname(self, val):
        self._groupname = val

    # Data processing #

    def process(self, dataIn=None):
        if self._filepath is None or self._groupname is None:
            return None
        if not os.path.exists(self._filepath):
            return None

        try:
            data = datadict_from_hdf5(self._filepath,
                                      groupname=self.groupname,
                                      n_retries=self.nRetries,
                                      retry_delay=self.retryDelay)
        except OSError:
            # TODO needs logging
            return None

        title = f"{self.filepath}"
        data.add_meta('title', title)
        self.nLoadedRecords = data.nrecords()

        if super().process(dataIn=data) is None:
            return None

        return dict(dataOut=data)


class DDH5Writer(object):
    """Context manager for writing data to DDH5.
    Based on typical needs in taking data in an experimental physics lab.

    Example usage::
        >>> data = DataDict(
        ...     x = dict(unit='x_unit'),
        ...     y = dict(unit='y_unit', axes=['x'])
        ... )
        ... with DDH5Writer('./data/', data, name='Test') as writer:
        ...     for x in range(10):
        ...         writer.add_data(x=x, y=x**2)
        Data location: ./data/2020-06-05/2020-06-05_0001_Example/2020-06-05_0001_Test.ddh5

    :param basedir: The root directory in which data is stored.
        :meth:`.create_file_structure` is creating the structure inside this root and
        determines the file name of the data. The default structure implemented here is
        ``<root>/YYYY-MM-DD/YYYY-MM-DD_<idx>_<name>/YYYY-MM-DD_<idx>_<name>.ddh5``,
        where <idx> is the automatically increasing number of this dataset in the day
        folder and <name> is the value of parameter `name`. To change this, re-implement
        :meth:`.create_file_structure`.
    :param datadict: initial data object. Must contain at least the structure of the
        data to be able to use :meth:`add_data` to add data.
    :param groupname: name of the top-level group in the file container. An existing
        group of that name will be deleted.
    :param name: name of this dataset. Used in path/file creation and added as meta data.
    """

    # TODO: need an operation mode for not keeping data in memory.
    # TODO: a mode for working with pre-allocated data

    def __init__(self, basedir: str,
                 datadict: DataDict,
                 groupname: str = 'data',
                 name: Optional[str] = None):
        """Constructor for :class:`.DDH5Writer`"""

        self.basedir = basedir
        self.datadict = datadict
        self.inserted_rows = 0
        self.name = name
        self.groupname = groupname

        self.file_base: Optional[str] = None
        self.file_path: Optional[str] = None
        self.file: Optional[h5py.File] = None

        self.datadict.add_meta('dataset.name', name)

    def __enter__(self):
        self.file_base = self.create_file_structure()
        self.file_path = self.file_base + f"{DATAFILEXT}"
        print('Data location: ', self.file_path)

        self.file = h5py.File(self.file_path, mode='a', libver='latest')
        init_file(self.file, self.groupname)
        add_cur_time_attr(self.file, name='last_change')
        add_cur_time_attr(self.file[self.groupname], name='last_change')

        if self.datadict.nrecords() > 0:
            write_data_to_file(self.datadict, self.file, groupname=self.groupname,
                               append_mode=AppendMode.none)
            self.inserted_rows = self.datadict.nrecords()

        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        add_cur_time_attr(self.file[self.groupname], name='close')
        self.file.close()

    def create_file_structure(self) -> str:
        """Determine the filepath and create all subfolders.

        :returns: the filepath (without extension) of the data file.
        """
        day_folder_path = os.path.join(self.basedir, time.strftime("%Y-%m-%d"))
        os.makedirs(day_folder_path, exist_ok=True)

        filebase = time.strftime("%Y-%m-%d_")
        existing_datafolders = [f for f in os.listdir(day_folder_path)
                                if f[:len(filebase)] == filebase]
        prev_idxs = [int(f[len(filebase):len(filebase)+4]) for f in existing_datafolders]
        if len(prev_idxs) == 0:
            new_idx = 1
        else:
            new_idx = max(prev_idxs) + 1
        filebase += f"{new_idx:04}"
        if self.name is not None:
            filebase += f"_{self.name}"

        data_folder_path = os.path.join(day_folder_path, filebase)
        os.makedirs(data_folder_path, exist_ok=True)

        return os.path.join(data_folder_path, filebase)

    def add_data(self, **kwargs: Any):
        """Add data to the file (and the internal `DataDict`).

        Requires one keyword argument per data field in the `DataDict`, with
        the key being the name, and value the data to add. It is required that
        all added data has the same number of 'rows', i.e., the most outer dimension
        has to match for data to be inserted faithfully.
        If some data is scalar and others are not, then the data should be reshaped
        to (1, ) for the scalar data, and (1, ...) for the others; in other words,
        an outer dimension with length 1 is added for all.
        """
        self.datadict.add_data(**kwargs)

        if self.inserted_rows > 0:
            mode = AppendMode.new
        else:
            mode = AppendMode.none

        if self.datadict.nrecords() > 0:
            write_data_to_file(self.datadict,
                               self.file,
                               groupname=self.groupname,
                               append_mode=mode)
            self.inserted_rows = self.datadict.nrecords()
            add_cur_time_attr(self.file, name='last_change')
            add_cur_time_attr(self.file[self.groupname], name='last_change')
