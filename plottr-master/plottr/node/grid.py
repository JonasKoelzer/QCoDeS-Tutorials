"""
grid.py

A node and widget for placing data onto a grid (or not).
"""

from enum import Enum, unique

from typing import Tuple, Dict, Any, List, Union

from plottr import QtGui, Signal, Slot
from .node import Node, NodeWidget, updateOption, updateGuiFromNode
from ..data import datadict as dd
from ..data.datadict import DataDict, MeshgridDataDict, DataDictBase
from plottr.icons import gridIcon

__author__ = 'Wolfgang Pfaff'
__license__ = 'MIT'


#: Type for additional options when specifying the shape
SpecShapeType = Dict[str, Tuple[Union[str, int], ...]]


@unique
class GridOption(Enum):
    """Options for how to grid data."""

    #: don't put on a grid
    noGrid = 0

    #: guess the shape of the grid
    guessShape = 1

    #: manually specify the shape of the grid
    specifyShape = 2


class ShapeSpecificationWidget(QtGui.QWidget):
    """A widget that allows the user to specify a grid shape.

    Note that this widget in this form knows nothing about any underlying data,
    and does not perform any checking of validity for submitted shapes.
    Such functionality would need to be implemented by users or inheriting
    classes.
    """

    #: signal that is emitted when we want to communicate a new shape
    newShapeNotification = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._axes = []
        self._widgets = {}
        self._processChanges = True

        self.layout = QtGui.QFormLayout()
        self.confirm = QtGui.QPushButton('set')
        self.layout.addRow(self.confirm)
        self.setLayout(self.layout)

        self.confirm.clicked.connect(self.signalShape)

    def signalShape(self):
        """When called, emit the current shape as signal"""
        self.newShapeNotification.emit(self.getShape())

    def _addAxis(self, idx, name):
        nameWidget = QtGui.QComboBox()
        for j, bx in enumerate(self._axes):
            nameWidget.addItem(bx)
        nameWidget.setCurrentText(name)

        dimLenWidget = QtGui.QSpinBox()
        dimLenWidget.setMinimum(1)
        dimLenWidget.setMaximum(999999)
        self._widgets[idx] = {
            'name': nameWidget,
            'shape': dimLenWidget,
        }
        self.layout.insertRow(idx, nameWidget, dimLenWidget)

        nameWidget.currentTextChanged.connect(
            lambda x: self._processAxisChange(idx, x)
        )

    def setAxes(self, axes: List[str]):
        """Specify a set of axis dimensions

        If the axes do not match the previous ones, delete all
        widgets and recreate.
        """
        if axes != self._axes:
            self._axes = axes

            for i in range(self.layout.rowCount() - 1):
                self._widgets[i]['name'].deleteLater()
                self._widgets[i]['shape'].deleteLater()
                self.layout.removeRow(0)

            self._widgets = {}

            for i, ax in enumerate(axes):
                self._addAxis(i, ax)

    def _unusedAxes(self):
        names = self._axes.copy()
        for k, v in self._widgets.items():
            ax = v['name'].currentText()
            if ax in names:
                del names[names.index(ax)]
        return names

    def _axisIndexFromName(self, name, excludeIdxs=[]):
        for k, v in self._widgets.items():
            if k not in excludeIdxs and v['name'].currentText() == name:
                return k

    def _processAxisChange(self, idx, newName):
        if not self._processChanges:
            return

        prevIdx = self._axisIndexFromName(newName, excludeIdxs=[idx])
        unused = self._unusedAxes()
        if prevIdx is not None and len(unused) > 0:
            self._processChanges = False
            self._widgets[prevIdx]['name'].setCurrentText(unused[0])
            self._processChanges = True

    def setShape(self, shape: Dict[str, Tuple[Union[str, int], ...]]):
        """ Set the shape, will be reflected in the values set in the widgets.

        :param shape: A dictionary with keys `order` and `shape`. The value
            of `order` must be a tuple with the axes names, ordered as desired.
            The value of `shape` is a tuple with the size of each axis
            dimension, in the order given by `order`.
        """
        if 'order' in shape and 'shape' in shape:
            self._processChanges = False
            for i, (o, s) in enumerate(zip(shape['order'], shape['shape'])):
                self._widgets[i]['name'].setCurrentText(o)
                self._widgets[i]['shape'].setValue(s)
            self._processChanges = True

    def getShape(self) -> Dict[str, Tuple[Union[str, int], ...]]:
        """get the currently specified shape.

        :returns: a dictionary with keys `order` and `shape`.
            the `order` value is a tuple with the axis names in order,
            and the `shape` value is the shape tuple of the grid, in the order
            as specified in the `order` value.
        """
        order = []
        shape = []
        for k, v in self._widgets.items():
            order.append(v['name'].currentText())
            shape.append(v['shape'].value())

        return {'order': tuple(order), 'shape': tuple(shape)}

    def enableEditing(self, enable):
        for ax, widgets in self._widgets.items():
            widgets['name'].setEnabled(enable)
            widgets['shape'].setEnabled(enable)
        self.confirm.setEnabled(enable)


class GridOptionWidget(QtGui.QWidget):
    """A widget that allows the user to specify how to grid data."""

    optionSelected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._emitUpdate = True

        #  make radio buttons and layout
        self.buttons = {
            GridOption.noGrid: QtGui.QRadioButton('No grid'),
            GridOption.guessShape: QtGui.QRadioButton('Guess shape'),
            GridOption.specifyShape: QtGui.QRadioButton('Specify shape'),
        }

        btnLayout = QtGui.QVBoxLayout()
        self.btnGroup = QtGui.QButtonGroup(self)

        for opt in GridOption:
            btn = self.buttons[opt]
            self.btnGroup.addButton(btn, opt.value)
            btnLayout.addWidget(btn)

        # make shape spec widget
        self.shapeSpec = ShapeSpecificationWidget()
        shapeLayout = QtGui.QVBoxLayout()
        shapeLayout.addWidget(self.shapeSpec)
        shapeBox = QtGui.QGroupBox()
        shapeBox.setLayout(shapeLayout)

        # Widget layout
        layout = QtGui.QVBoxLayout()
        layout.addLayout(btnLayout)
        layout.addWidget(shapeBox)
        layout.addStretch()
        self.setLayout(layout)

        # Connect signals/slots #
        self.btnGroup.buttonToggled.connect(self.gridButtonSelected)
        self.shapeSpec.confirm.clicked.connect(self.shapeSpecified)

        # Default settings
        self.buttons[GridOption.noGrid].setChecked(True)
        self.enableShapeEdit(False)

    def getGrid(self) -> Tuple[GridOption, Dict[str, Any]]:
        """Get grid option from the current widget selections

        :returns: the grid specification, and the options that go with it.
            options are empty unless the grid specification is
            :mem:`GridOption.specifyShape`. In that case the additional options
            are `order` and `shape` as returned by :mem:`getShape`.
        """
        activeBtn = self.btnGroup.checkedButton()
        activeId = self.btnGroup.id(activeBtn)
        opts = {}

        if GridOption(activeId) == GridOption.specifyShape:
            opts = self.shapeSpec.getShape()

        return GridOption(activeId), opts

    def setGrid(self, grid: Tuple[GridOption, Dict[str, Any]]):
        """Set the grid specification in the UI.

        :param grid: Tuple of the :class:`GridOption` and additional options.
            if `specifyShape` is the selection option, additional options need
            to be `order` and `shape`.
        """
        # This function should not trigger an emission for an update.
        # We only want that when the user sets the grid in the UI,
        # to avoid recursive calls
        self._emitUpdate = False

        method, opts = grid
        for k, btn in self.buttons.items():
            if k == method:
                btn.setChecked(True)

        self._emitUpdate = True

    @Slot(QtGui.QAbstractButton, bool)
    def gridButtonSelected(self, btn: QtGui.QAbstractButton, checked: bool):
        """Process a change in grid option radio box selection.
        Only has an effect when the change was done manually, and is not
        coming from the node.

        Will result in emission of :mem:`optionSelected` and enable/disable
        the shape specification widget depending on the new selection.
        """
        if checked:
            # only emit the signal when the update is from the UI
            if self._emitUpdate:
                self.signalGridOption(self.getGrid())

            if GridOption(self.btnGroup.id(btn)) == GridOption.specifyShape:
                self.enableShapeEdit(True)
            else:
                self.enableShapeEdit(False)

            self._emitUpdate = True

    @Slot()
    def shapeSpecified(self):
        self.signalGridOption(self.getGrid())

    def signalGridOption(self, grid):
        self.optionSelected.emit(grid)

    def setAxes(self, axes: List[str]):
        """Set the available axis dimensions."""
        self.shapeSpec.setAxes(axes)
        if self.getGrid()[0] == GridOption.specifyShape:
            self.enableShapeEdit(True)
        else:
            self.enableShapeEdit(False)

    def setShape(self, shape: SpecShapeType):
        """Set the shape of the grid."""
        self.shapeSpec.setShape(shape)

    def enableShapeEdit(self, enable: bool):
        """Enable/disable shape editing"""
        self.shapeSpec.enableEditing(enable)


class DataGridderNodeWidget(NodeWidget):
    """Node widget for :class:`DataGridderNode`."""

    icon = gridIcon

    def __init__(self, node: Node = None):
        super().__init__(embedWidgetClass=GridOptionWidget)

        self.optSetters = {
            'grid': self.setGrid,
        }
        self.optGetters = {
            'grid': self.getGrid,
        }
        self.widget.optionSelected.connect(
            lambda x: self.signalOption('grid')
        )

    def getGrid(self):
        return self.widget.getGrid()

    def setGrid(self, grid):
        self.widget.setGrid(grid)

    @updateGuiFromNode
    def setAxes(self, axes):
        self.widget.setAxes(axes)

    @updateGuiFromNode
    def setShape(self, shape):
        self.widget.setShape(shape)


class DataGridder(Node):
    """
    A node that can put data onto or off a grid.
    Has one property: :attr:`grid`. Its possible values are governed by a main option,
    plus (optional) additional options.
    """

    nodeName = "Gridder"
    uiClass = DataGridderNodeWidget

    #: signal emitted when we have programatically determined a shape for the data.
    shapeDetermined = Signal(dict)

    axesList = Signal(list)

    def __init__(self, *arg, **kw):

        self._grid = GridOption.noGrid, {}
        self._shape = None
        self._invalid = False

        super().__init__(*arg, **kw)

    # Properties

    @property
    def grid(self):
        """Specification for how to grid the data. Consists of a main option
        and (optional) additional options.

        The main option is of type :class:`GridOption`, and the additional options
        are given as a dictionary. Assign as tuple, like::

        >>> dataGridder.grid = GridOption.<option>, dict((**options)

        All types of :class:`GridOption` are valid main options:

            * :attr:`GridOption.noGrid` --
                will leave tabular data as is, and flatten gridded data to result
                in tabular data

            * :attr:`GridOption.guessGrid` --
                use :func:`.guess_shape_from_datadict` and :func:`.datadict_to_meshgrid`
                to infer the grid, if the input data is tabular.

            * :attr:`GridOption.specifyShape` --
                reshape the data using a specified shape.

        Some types may required additional options.
        At the moment, this is only the case for :attr:`GridOption.specifyShape`.
        Manual specification of the shape requires two additional options, `order` and `shape`:

            * `order` --
                a list of the input data axis dimension names, in the
                internal order of the input data array.
                This order is used to transpose the data before re-shaping with the
                `shape` information.
                Often this is simply the axes list; then the transpose has no
                effect.
                A different order needed when the the data to be gridded is not in `C` order,
                i.e., when the axes order given in the DataDict is not from
                slowest changing to fastest changing.

            * `shape` --
                a tuple of integers that can be used to reshape the input
                data to obtain a grid.
                Must be in the same order as `order` to work correctly.

        See :func:`.data.datadict.datadict_to_meshgrid` for additional notes;
        `order` will be passed to `inner_axis_order` in that function, and
        `shape` to `target_shape`.
        """
        return self._grid

    @grid.setter
    @updateOption('grid')
    def grid(self, val: Tuple[GridOption, Dict[str, Any]]):
        """set the grid option. does some elementary type checking, but should
        probably be refined a bit."""

        try:
            method, opts = val
        except TypeError:
            raise ValueError(f"Invalid grid specification.")

        if not method in GridOption:
            raise ValueError(f"Invalid grid method specification.")

        if not isinstance(opts, dict):
            raise ValueError(f"Invalid grid options specification.")

        self._grid = val

    # Processing

    def validateOptions(self, data: Any):
        """Currently, does not perform checks beyond those of the parent class.
        """
        if not super().validateOptions(data):
            return False

        return True

    def process(self, dataIn: DataDict = None):
        """Process the data."""

        # TODO: what would be nice is to change the correct inner axis order
        #   in the widget when we guess the shape. unfortunately, we currently
        #   don't get that information from the guess function, and it is also
        #   not reflected in the resulting data.

        data = dataIn
        if data is None:
            return None

        data = super().process(dataIn=dataIn)
        if data is None:
            return None
        data = data['dataOut'].copy()
        self.axesList.emit(data.axes())

        dout = None
        method, opts = self._grid
        order = opts.get('order', data.axes())

        if isinstance(data, DataDict):
            if method is GridOption.noGrid:
                dout = data.expand()
            elif method is GridOption.guessShape:
                dout = dd.datadict_to_meshgrid(data)
            elif method is GridOption.specifyShape:
                dout = dd.datadict_to_meshgrid(
                    data, target_shape=opts['shape'],
                    inner_axis_order=order,
                )

        elif isinstance(data, MeshgridDataDict):
            if method is GridOption.noGrid:
                dout = dd.meshgrid_to_datadict(data)
            elif method is GridOption.guessShape:
                dout = data
            elif method is GridOption.specifyShape:
                self.logger().warning(
                    f"Data is already on grid. Ignore shape.")
                dout = data

        else:
            self.logger().error(
                f"Unknown data type {type(data)}.")
            return None

        if dout is None:
            return None

        if hasattr(dout, 'shape'):
            self.shapeDetermined.emit({'order': order,
                                       'shape': dout.shape()})

        return dict(dataOut=dout)

    # Setup UI

    def setupUi(self):
        super().setupUi()
        self.axesList.connect(self.ui.setAxes)
        self.shapeDetermined.connect(self.ui.setShape)
