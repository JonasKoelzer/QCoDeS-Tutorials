"""dim_reducer.py

nodes and widgets for reducing data dimensionality.
"""
from typing import Dict, Any, Tuple, Type
from enum import Enum, unique
from collections import OrderedDict

import numpy as np

from .node import Node, updateOption, NodeWidget
from ..data.datadict import MeshgridDataDict, DataDict, DataDictBase
from .. import QtGui, QtCore
from plottr.icons import xySelectIcon

__author__ = 'Wolfgang Pfaff'
__license__ = 'MIT'


# Some helpful reduction functions

def sliceAxis(arr: np.ndarray, sliceObj: slice, axis: int) -> np.ndarray:
    """
    return the array where the axis with the given index is sliced
    with the given slice object.

    :param arr: input array
    :param sliceObj: slice object to use on selected dimension
    :param axis: dimension of the array to apply slice to
    :return: array after slicing
    """
    slices = [np.s_[::] for i in arr.shape]
    slices[axis] = sliceObj
    return arr[tuple(slices)]


def selectAxisElement(arr: np.ndarray, index: int, axis: int) -> np.ndarray:
    """
    return the squeezed array where the given axis has been reduced to its
    value with the given index.

    :param arr: input array
    :param index: index of the element to keep
    :param axis: dimension on which to perform the reduction
    :return: reduced array
    """
    return np.squeeze(sliceAxis(arr, np.s_[index:index+1:], axis))


# Translation between reduction functions and convenient naming
@unique
class ReductionMethod(Enum):
    """Built-in reduction methods"""
    elementSelection = 'select element'
    average = 'average'


#: mapping from reduction method Enum to functions
reductionFunc = {
    ReductionMethod.elementSelection: selectAxisElement,
    ReductionMethod.average: np.mean,
}

class DimensionAssignmentWidget(QtGui.QTreeWidget):
    """
    A Widget that allows to assign options ('roles') to dimensions of a
    dataset.
    In this base version, there are no options included.
    This needs to be done by inheriting classes.
    """

    rolesChanged = QtCore.pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setColumnCount(4)
        self.setHeaderLabels(['Dimension', 'Role', 'Options', 'Info'])

        self._dataStructure = None
        self._dataShapes = None
        self._dataType = None
        self._currentRoles = {}

        #: This is a flag to control whether we need to emit signals when
        #: a role has changed. broadly speaking, this is only desired when
        #: the change comes from the user interacting with the UI, otherwise
        #: it might lead to undesired recursion.
        self.emitRoleChangeSignal = True

        self.choices = {}
        self.availableChoices = OrderedDict({
            DataDictBase: ['None', ],
            DataDict: [],
            MeshgridDataDict: [],
        })

    def clear(self):
        """
        Clear the widget, delete all accessory widgets.
        """
        super().clear()

        for n, opts in self.choices.items():
            opts['roleSelectionWidget'].deleteLater()
            del opts['roleSelectionWidget']

            if 'optionsWidget' in opts:
                if opts['optionsWidget'] is not None:
                    opts['optionsWidget'].deleteLater()
                del opts['optionsWidget']

        self._dataStructure = None
        self._dataShapes = None
        self._dataType = None
        self.choices = {}

    def updateSizes(self):
        """update column widths to fit content."""
        for i in range(4):
            self.resizeColumnToContents(i)

    def setData(self, structure: DataDictBase,
                shapes: dict, dtype: Type[DataDictBase]):
        """
        set data: add all dimensions to the list, and populate choices.

        :param data: DataDict object
        """
        if structure is None:
            self.clear()
            return

        if DataDictBase.same_structure(structure, self._dataStructure) \
                and shapes == self._dataShapes \
                and dtype == self._dataType:
            return

        self.clear()
        self._dataType = dtype
        self._dataShapes = shapes
        self._dataStructure = structure
        self._currentRoles = {}

        for ax in self._dataStructure.axes():
            self.addDimension(ax)

    def addDimension(self, name: str):
        """
        add a new dimension.

        :param name: name of the dimension.
        """
        item = QtGui.QTreeWidgetItem([name, '', '', ''])
        self.addTopLevelItem(item)

        combo = QtGui.QComboBox()
        for t, opts in self.availableChoices.items():
            if t == self._dataType or issubclass(self._dataType, t):
                for o in opts:
                    combo.addItem(o)

        combo.setMinimumSize(50, 22)
        combo.setMaximumHeight(22)
        self.setItemWidget(item, 1, combo)
        self.updateSizes()

        self.choices[name] = {
            'roleSelectionWidget': combo,
            'optionsWidget': None,
        }
        combo.currentTextChanged.connect(
            lambda x: self.processSelectionChange(name, x)
        )
        self.setDimInfo(name, '')

    def processSelectionChange(self, name: str, val: str):
        """
        Call to notify that a dimension's role should be changed.
        any specific actions should be implemented in :func:`setRole`.

        :param name: name of the dimension
        :param val: new role name
        """

        # we need a flag here to not emit signals when we recursively change
        # roles. Sometimes we do, because roles are not independent for the
        # dims.
        if self.emitRoleChangeSignal:
            self.emitRoleChangeSignal = False
            self.setRole(name, val)
            self.rolesChanged.emit(self.getRoles())
            self.emitRoleChangeSignal = True

    def setRole(self, dim: str, role: str = None):
        """
        Set the role for a dimension, including options.

        :param dim: name of the dimension
        :param role: name of the role
        """
        curRole = self._currentRoles.get(dim, None)
        if curRole is None or curRole['role'] != role:
            self.choices[dim]['roleSelectionWidget'].setCurrentText(role)
            item = self.findItems(dim, QtCore.Qt.MatchExactly, 0)[0]

            if 'optionsWidget' in self.choices[dim]:
                w = self.choices[dim]['optionsWidget']
                if w is not None:
                    w.deleteLater()
                    self.choices[dim]['optionsWidget'] = None

            self.setItemWidget(item, 2, None)
            self.setDimInfo(dim, '')

            self._currentRoles[dim] = {
                'role' : role,
                'options' : {},
            }

    def getRole(self, name: str) -> Tuple[str, Any]:
        """
        Get the current role and its options for a dimension.
        :param name: 
        :return: 
        """
        role = self.choices[name]['roleSelectionWidget'].currentText()
        opts = {}
        return role, opts

    def getRoles(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all roles as set in the UI.
        :return: Dictionary with information on all current roles/options.
        """
        ret = {}
        for name, val in self.choices.items():
            role, opts = self.getRole(name)
            ret[name] = {
                'role': role,
                'options': opts,
            }
        return ret

    @QtCore.pyqtSlot(str, str)
    def setDimInfo(self, dim: str, info: str = ''):
        try:
            item = self.findItems(dim, QtCore.Qt.MatchExactly, 0)[0]
            item.setText(3, info)
        except IndexError:
            pass

    @QtCore.pyqtSlot(dict)
    def setDimInfos(self, infos: Dict[str, str]):
        for ax, info in infos.items():
            self.setInfo(ax, info)


class DimensionReductionAssignmentWidget(DimensionAssignmentWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.availableChoices[MeshgridDataDict] += [
            ReductionMethod.average.value,
            ReductionMethod.elementSelection.value,
        ]

    def getRole(self, name: str):
        role, opts = super().getRole(name)

        if role == ReductionMethod.elementSelection.value:
            opts['index'] = self.choices[name]['optionsWidget'].value()

        return role, opts

    def setRole(self, dim: str, role: str = None, **kw):
        super().setRole(dim, role)

        # at this point, we've already populated the dropdown.
        # this is now for additional options
        item = self.findItems(dim, QtCore.Qt.MatchExactly, 0)[0]

        if role == ReductionMethod.elementSelection.value:
            value = kw.get('index', 0)

            # only create the slider widget if it doesn't exist yet
            if self.itemWidget(item, 2) is None:
                # get the number of elements in this dimension
                axidx = self._dataStructure.axes().index(dim)
                naxvals = self._dataShapes[dim][axidx]

                w = self.elementSelectionSlider(nvals=naxvals, value=value)
                w.valueChanged.connect(
                    lambda x: self.elementSelectionSliderChange(dim))

                w.setMinimumSize(150, 22)
                w.setMaximumHeight(22)

                self.choices[dim]['optionsWidget'] = w
                self.setItemWidget(item, 2, w)
                self.updateSizes()

            self._setElementSelectionInfo(dim)

    def elementSelectionSlider(self, nvals: int, value: int = 0):
        w = QtGui.QSlider(0x01)
        w.setMinimum(0)
        w.setMaximum(nvals - 1)
        w.setSingleStep(1)
        w.setPageStep(1)
        w.setTickInterval(max(1, nvals//10))
        w.setTickPosition(QtGui.QSlider.TicksBelow)
        w.setValue(value)
        return w

    def elementSelectionSliderChange(self, dim: str):
        self._setElementSelectionInfo(dim)
        roles = self.getRoles()
        self.rolesChanged.emit(roles)

    def _setElementSelectionInfo(self, dim):
        # get the number of elements in this dimension
        roles = self.getRoles()
        axidx = self._dataStructure.axes().index(dim)
        naxvals = self._dataShapes[dim][axidx]
        idx = roles[dim]['options']['index']
        self.setDimInfo(dim, f"({idx + 1}/{naxvals})")


class XYSelectionWidget(DimensionReductionAssignmentWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.availableChoices[DataDictBase] += ["x-axis", "y-axis"]

    def setRole(self, dim: str, role: str = None, **kw):
        super().setRole(dim, role, **kw)

        # there can only be one x and y axis element.
        if role in ['x-axis', 'y-axis']:
            allRoles = self.getRoles()
            for d, r in allRoles.items():
                if d == dim:
                    continue
                if r['role'] == role:
                    self.setRole(d, 'None')


class DimensionReducerNodeWidget(NodeWidget):

    def __init__(self, node: Node = None):
        super().__init__(embedWidgetClass=DimensionReductionAssignmentWidget)

        self.optSetters = {
            'reductions': self.setReductions,
        }
        self.optGetters = {
            'reductions': self.getReductions,
        }

        self.widget.rolesChanged.connect(
            lambda x: self.signalOption('reductions'))

    def getReductions(self):
        roles = self.widget.getRoles()
        reductions = {}
        for dimName, rolesOptions in roles.items():
            role = rolesOptions['role']
            opts = rolesOptions['options']
            method = ReductionMethod(role)
            if method is not None:
                reductions[dimName] = method, [], opts

        return reductions

    def setReductions(self, reductions):
        for dimName, (method, arg, kw) in reductions.items():
            role = method.value
            self.widget.setRole(dimName, role, **kw)

        for dimName, _ in self.widget.getRoles().items():
            if dimName not in reductions.keys():
                self.widget.setRole(dimName, 'None')

    def setData(self, structure, shapes, dtype):
        self.widget.setData(structure, shapes, dtype)


class DimensionReducer(Node):
    """
    A Node that allows the user to reduce the dimensionality of input data.

    Each axis can be assigned an arbitrary reduction function that will reduce
    the axis to a single value. For each assigned reduction the dimension
    shrinks by 1.

    If the input is not GridData, data is just passed through, but we delete the
    axes present in reductions.

    If the output contains invalid entries, they will be masked.

    Properties are:

    :targetNames: ``List[str]`` or ``None``.
        reductions affect all dependents that are given. If None, will apply
        to all dependents.
    :reductions: ``Dict[str, (callable, *args, **kwargs)]``
        reduction functions. Keys are the axis names the reductions are applied
        to; values are tuples of the reduction function, and optional
        arguments and kw-arguments.
        The function can also be via :class:`ReductionMethod`.
        The function must accept an ``axis = <int>`` keyword, and must return
        an array of dimensionality that is reduced by one compared to its
        input.
    """

    nodeName = 'DimensionReducer'
    uiClass = DimensionReducerNodeWidget

    #: A signal that emits (structure, shapes, type) when data structure has
    #: changed.
    newDataStructure = QtCore.pyqtSignal(object, object, object)

    def __init__(self, *arg, **kw):
        self._reductions = {}
        self._targetNames = None
        self._dataStructure = None

        super().__init__(*arg, **kw)

    # Properties

    @property
    def reductions(self):
        return self._reductions

    @reductions.setter
    @updateOption('reductions')
    def reductions(self, val):
        self._reductions = val

    @property
    def targetNames(self):
        return self._targetNames

    @targetNames.setter
    @updateOption()
    def targetNames(self, val):
        self._targetNames = val

    # Data processing

    def _applyDimReductions(self, data):
        """Apply the reductions"""
        if self._targetNames is not None:
            dnames = self._targetNames
        else:
            dnames = data.dependents()

        if not isinstance(data, MeshgridDataDict):
            self.logger().debug(f"Data is not on a grid. "
                                f"Reduction functions are ignored, "
                                f"axes will simply be removed.")

        for n in dnames:
            for ax, reduction in self._reductions.items():
                if reduction is not None:
                    fun, arg, kw = reduction
                else:
                    fun, arg, kw = None, [], {}

                try:
                    idx = data[n]['axes'].index(ax)
                except IndexError:
                    self.logger().info(f'{ax} specified for reduction, '
                                       f'but not present in data; ignore.')

                kw['axis'] = idx

                # actual operation is only done if the data is on a grid.
                if isinstance(data, MeshgridDataDict):

                    # check that the new shape is actually correct
                    # get target shape by removing the right axis
                    targetShape = list(data[n]['values'].shape)
                    del targetShape[idx]
                    targetShape = tuple(targetShape)

                    # support for both pre-defined and custom functions
                    if isinstance(fun, ReductionMethod):
                        funCall = reductionFunc[fun]
                    else:
                        funCall = fun

                    newvals = funCall(data[n]['values'], *arg, **kw)
                    if newvals.shape != targetShape:
                        self.logger().error(
                            f'Reduction on axis {ax} did not result in the '
                            f'right data shape. ' +
                            f'Expected {targetShape} but got {newvals.shape}.'
                            )
                        return None
                    data[n]['values'] = newvals

                    # since we are on a meshgrid, we also need to reduce
                    # the dimensions of the coordinate meshes
                    for ax in data[n]['axes']:
                        if len(data.data_vals(ax).shape) > len(targetShape):
                            newaxvals = funCall(data[ax]['values'], *arg, **kw)
                            data[ax]['values'] = newaxvals

                del data[n]['axes'][idx]

        data = data.sanitize()
        data.validate()
        return data

    def validateOptions(self, data):
        """
        Checks performed:
        * each item in reduction must be of the form (fun, [*arg], {**kw}),
          with arg and kw being optional; if the tuple is has length 2,
          the second element is taken as the arg-list.
          The function can be of type :class:`.ReductionMethod`.
        """

        delete = []
        for ax, reduction in self._reductions.items():

            if reduction is None:
                if isinstance(data, MeshgridDataDict):
                    self.logger().warning(f'Reduction for axis {ax} is None. '
                                          f'Removing.')
                    delete.append(ax)
                else:
                    pass
                continue

            try:
                fun = reduction[0]
                if len(reduction) == 1:
                    arg = []
                    kw = {}
                elif len(reduction) == 2:
                    arg = reduction[1]
                    kw = {}
                else:
                    arg = reduction[1]
                    kw = reduction[2]
            except:
                self.logger().warning(
                    f'Reduction for axis {ax} not in the right format.'
                )
                return False

            if not callable(fun) and not isinstance(fun, ReductionMethod):
                self.logger().error(
                    f'Invalid reduction method for axis {ax}. '
                    f'Needs to be callable or a ReductionMethod type.'
                )
                return False

            # reduction methods are only defined for grid data.
            # remove reduction methods if we're not on a grid.
            if isinstance(fun, ReductionMethod) and not isinstance(data, MeshgridDataDict):
                self.logger().info(f'Reduction set for axis {ax} is only suited for '
                                   f'grid data. Removing.')
                delete.append(ax)

            # set the reduction in the correct format.
            self._reductions[ax] = (fun, arg, kw)

        for ax in delete:
            del self._reductions[ax]

        return True

    def process(self, dataIn: DataDictBase = None):
        if dataIn is None:
            return None

        data = super().process(dataIn=dataIn)

        if data is None:
            return None

        data = data['dataOut'].copy()
        data = data.mask_invalid()
        data = self._applyDimReductions(data)

        return dict(dataOut=data)

    # FIXME: include connection to a method that helps updating sliders etc.
    def setupUi(self):
        super().setupUi()
        self.newDataStructure.connect(self.ui.setData)


class XYSelectorNodeWidget(NodeWidget):

    icon = xySelectIcon

    def __init__(self, node: Node = None):
        super().__init__(embedWidgetClass=XYSelectionWidget)

        self.optSetters = {
            'dimensionRoles': self.setRoles,
        }
        self.optGetters = {
            'dimensionRoles': self.getRoles,
        }

        self.widget.rolesChanged.connect(
            lambda x: self.signalOption('dimensionRoles')
        )

    def getRoles(self):
        widgetRoles = self.widget.getRoles()
        roles = {}
        for dimName, rolesOptions in widgetRoles.items():
            role = rolesOptions['role']
            opts = rolesOptions['options']

            if role in ['x-axis', 'y-axis']:
                roles[dimName] = role

            elif role in [e.value for e in ReductionMethod]:
                method = ReductionMethod(role)
                if method is not None:
                    roles[dimName] = method, [], opts

        return roles

    def setRoles(self, roles):
        # when this is called, we do not want the UI to signal changes.
        self.widget.emitRoleChangeSignal = False

        for dimName, role in roles.items():
            if role in ['x-axis', 'y-axis']:
                self.widget.setRole(dimName, role)
            elif isinstance(role, tuple):
                method, arg, kw = role
                methodName = method.value
                self.widget.setRole(dimName, methodName, **kw)
            elif role is None:
                self.widget.setRole(dimName, 'None')

        for dimName, _ in self.widget.getRoles().items():
            if dimName not in roles.keys():
                self.widget.setRole(dimName, 'None')

        self.widget.emitRoleChangeSignal = True

    def setData(self, structure, shapes, dtype):
        self.widget.setData(structure, shapes, dtype)


class XYSelector(DimensionReducer):

    nodeName = 'XYSelector'
    uiClass = XYSelectorNodeWidget

    def __init__(self, *arg, **kw):
        self._xyAxes = (None, None)
        super().__init__(*arg, **kw)

    @property
    def xyAxes(self):
        return self._xyAxes

    @xyAxes.setter
    @updateOption('xyAxes')
    def xyAxes(self, val):
        self._xyAxes = val

    @property
    def dimensionRoles(self):
        dr = {}
        if self.xyAxes[0] is not None:
            dr[self.xyAxes[0]] = 'x-axis'
        if self.xyAxes[1] is not None:
            dr[self.xyAxes[1]] = 'y-axis'
        for dim, red in self.reductions.items():
            dr[dim] = red
        return dr

    @dimensionRoles.setter
    @updateOption('dimensionRoles')
    def dimensionRoles(self, val):
        xy = [None, None]
        for dimName, role in val.items():
            if role == 'x-axis':
                xy[0] = dimName
            elif role == 'y-axis':
                xy[1] = dimName
            else:
                self._reductions[dimName] = role
        self._xyAxes = tuple(xy)

    def validateOptions(self, data):
        """
        Checks performed:
        * values for xAxis and yAxis must be axes that exist for the input
        data.
        * x/y axes cannot be the same
        * x/y axes cannot be reduced (will be removed from reductions)
        * all axes that are not x/y must be reduced (defaulting to
        selection of the first element)
        """

        if not super().validateOptions(data):
            return False
        availableAxes = data.axes()

        if len(availableAxes) > 0:
            if self._xyAxes[0] is None:
                self.logger().debug(
                    f'x-Axis is None. this will result in empty output data.')
                return False
            elif self._xyAxes[0] not in availableAxes:
                self.logger().warning(
                    f'x-Axis {self._xyAxes[0]} not present in data')
                return False

            if self._xyAxes[1] is None:
                self.logger().debug(f'y-Axis is None; result will be 1D')
            elif self._xyAxes[1] not in availableAxes:
                self.logger().warning(
                    f'y-Axis {self._xyAxes[1]} not present in data')
                return False
            elif self._xyAxes[1] == self._xyAxes[0]:
                self.logger().warning(f"y-Axis cannot be equal to x-Axis.")
                return False

        # below we actually mess with the reduction options, but
        # without using the decorated property.
        # make sure we emit the right signal at the end.
        reductionsChanged = False

        # Check: an axis marked as x/y cannot be also reduced.
        delete = []
        for n, _ in self._reductions.items():
            if n in self._xyAxes:
                self.logger().debug(
                    f"{n} has been selected as axis, cannot be reduced.")
                delete.append(n)
        for n in delete:
            del self._reductions[n]
            reductionsChanged = True

        # check: axes not marked as x/y should all be reduced.
        for ax in availableAxes:
            if ax not in self._xyAxes:
                if ax not in self._reductions:
                    self.logger().debug(
                        f"{ax} must be reduced. "
                        f"Default to selecting first element.")

                    # reductions are only supported on GridData
                    if isinstance(data, MeshgridDataDict):
                        red = (ReductionMethod.elementSelection, [],
                               dict(index=0))
                    else:
                        red = None

                    self._reductions[ax] = red
                    reductionsChanged = True

        # emit signal that we've changed things
        if reductionsChanged:
            self.optionChangeNotification.emit(
                {'dimensionRoles': self.dimensionRoles}
            )

        return True

    def process(self, **kw):
        data = kw['dataIn']
        if data is None:
            return None

        data = super().process(dataIn=data)
        if data is None:
            return None
        data = data['dataOut'].copy()

        if self._xyAxes[0] is not None and self._xyAxes[1] is not None:
            _kw = {self._xyAxes[0]: 0, self._xyAxes[1]: 1}
            data = data.reorder_axes(**_kw)

        # it is possible that UI options have been re-generated, while the
        # options in the node have not been changed. to make sure everything
        # is in sync, we simply set the UI options again here.
        if self.ui is not None:
            self.ui.setRoles(self.dimensionRoles)

        return dict(dataOut=data)
