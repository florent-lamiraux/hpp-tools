# -*- coding: utf-8 -*-
# This file is part of Eigen, a lightweight C++ template library
# for linear algebra.
#
# Copyright (C) 2009 Benjamin Schindler <bschindler@inf.ethz.ch>
#
# Eigen is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# Alternatively, you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of
# the License, or (at your option) any later version.
#
# Eigen is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public License or the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License and a copy of the GNU General Public License along with
# Eigen. If not, see <http://www.gnu.org/licenses/>.

# Pretty printers for Eigen::Matrix
# This is still pretty basic as the python extension to gdb is still pretty basic. 
# It cannot handle complex eigen types and it doesn't support any of the other eigen types
# Such as quaternion or some other type. 
# This code supports fixed size as well as dynamic size matrices

# To use it:
#
# * Create a directory and put the file as well as an empty __init__.py in 
#   that directory.
# * Create a ~/.gdbinit file, that contains the following:
#      python
#      import sys
#      sys.path.insert(0, '/path/to/eigen/printer/directory')
#      from printers import register_eigen_printers
#      register_eigen_printers (None)
#      end

import gdb
import re
import itertools
import sys

if sys.version_info[0] > 2:
    ### Python 3 stuff
    Iterator = object
    # Python 3 folds these into the normal functions.
    imap = map
    izip = zip
    # Also, int subsumes long
    long = int
else:
    ### Python 2 stuff
    class Iterator:
        """Compatibility mixin for iterators

        Instead of writing next() methods for iterators, write
        __next__() methods and use this mixin to make them work in
        Python 2 as well as Python 3.

        Idea stolen from the "six" documentation:
        <http://pythonhosted.org/six/#six.Iterator>
        """

        def next(self):
            return self.__next__()


class EigenMatrixPrinter:
    "Print Eigen Matrix or Array of some kind"

    def __init__(self, variety, val):
        "Extract all the necessary information"
        
        # Save the variety (presumably "Matrix" or "Array") for later usage
        self.variety = variety
        
        # The gdb extension does not support value template arguments - need to extract them by hand
        type = val.type
        if type.code == gdb.TYPE_CODE_REF:
            type = type.target()
        self.type = type.unqualified().strip_typedefs()
        tag = self.type.tag
        regex = re.compile('\<.*\>')
        m = regex.findall(tag)[0][1:-1]
        template_params = m.split(',')
        template_params = list(map(lambda x:x.replace(" ", ""), template_params))

        self.rows = int(template_params[1],0)
        self.cols = int(template_params[2],0)
        self.options = 0 # default value
        if len(template_params) > 3:
            self.options = template_params[3];
        
        self.rowMajor = (int(self.options) & 0x1)

        if self.rows == -1:
            self.rows = val['m_storage']['m_rows']

        if self.cols == -1:
            self.cols = val['m_storage']['m_cols']

        self.innerType = self.type.template_argument(0)

        self.val = val
        
        # Fixed size matrices have a struct as their storage, so we need to walk through this
        self.data = self.val['m_storage']['m_data']
        if self.data.type.code == gdb.TYPE_CODE_STRUCT:
            self.data = self.data['array']
            self.data = self.data.cast(self.innerType.pointer())
            
    class _iterator(Iterator):
        def __init__ (self, rows, cols, dataPtr, rowMajor):
            self.rows = rows
            self.cols = cols
            self.dataPtr = dataPtr
            self.currentRow = 0
            self.currentCol = 0
            self.rowMajor = rowMajor

        def __iter__ (self):
            return self

        def __next__(self):
        
            row = self.currentRow
            col = self.currentCol
            if self.rowMajor == 0:
                if self.currentCol >= self.cols:
                    raise StopIteration
                    
                self.currentRow = self.currentRow + 1
                if self.currentRow >= self.rows:
                    self.currentRow = 0
                    self.currentCol = self.currentCol + 1
            else:
                if self.currentRow >= self.rows:
                    raise StopIteration
                    
                self.currentCol = self.currentCol + 1
                if self.currentCol >= self.cols:
                    self.currentCol = 0
                    self.currentRow = self.currentRow + 1
                

            item = self.dataPtr.dereference()
            self.dataPtr = self.dataPtr + 1
            if (self.cols == 1): #if it's a column vector
                return ('[%d]' % (row,), item)
            elif (self.rows == 1): #if it's a row vector
                return ('[%d]' % (col,), item)
            return ('[%d,%d]' % (row, col), item)

    def children(self):
        
        return self._iterator(self.rows, self.cols, self.data, self.rowMajor)

    def to_string(self):
        return "Eigen::%s<%s,%d,%d,%s> (data ptr: %s)" % (self.variety, self.innerType, self.rows, self.cols, "RowMajor" if self.rowMajor else  "ColMajor", self.data)

class EigenRefPrinter:
    "Print Eigen Ref of some kind"

    def __init__(self, variety, val):
        "Extract all the necessary information"
        
        # Save the variety (presumably "Matrix" or "Array") for later usage
        self.variety = variety
        
        type = val.type
        if type.code == gdb.TYPE_CODE_REF:
            type = type.target()
        self.type = type.unqualified().strip_typedefs()
        self.referenced = type.template_argument(0)

        # The gdb extension does not support value template arguments - need to extract them by hand
        # tag = self.referenced.tag
        # regex = re.compile('\<.*\>')
        # m = regex.findall(tag)[0][1:-1]
        # template_params = m.split(',')
        # template_params = list(map(lambda x:x.replace(" ", ""), template_params))

        self.rows = int(self.referenced.template_argument(1))
        self.cols = int(self.referenced.template_argument(2))
        self.options = int(self.referenced.template_argument(3))
        # self.options = 0 # default value
        # if len(template_params) > 3:
            # self.options = template_params[3];
        
        self.rowMajor = (int(self.options) & 0x1)

        if self.rows == -1:
            self.rows = int(val['m_rows']['m_value'])

        if self.cols == -1:
            self.cols = int(val['m_cols']['m_value'])

        stride = val['m_stride']
        stride_type = val['m_stride'].type.unqualified().strip_typedefs()
        self.outer_stride = int(stride_type.template_argument(0))
        self.inner_stride = int(stride_type.template_argument(1))
        if self.outer_stride == -1:
            self.outer_stride = int(stride['m_outer']['m_value'])
        if self.inner_stride == -1:
            self.inner_stride = int(stride['m_inner']['m_value'])

        self.innerType = self.referenced.template_argument(0)

        self.val = val
        
        # Fixed size matrices have a struct as their storage, so we need to walk through this
        self.data = self.val['m_data']
        if self.data.type.code == gdb.TYPE_CODE_STRUCT:
            self.data = self.data['array']
            self.data = self.data.cast(self.innerType.pointer())
            
    class _iterator(Iterator):
        def __init__ (self, rows, cols, outer_stride, inner_stride, dataPtr, rowMajor):
            self.rows = rows
            self.cols = cols
            self.outer_stride = outer_stride
            self.inner_stride = inner_stride
            self.dataPtr = dataPtr
            self.currentRow = 0
            self.currentCol = 0
            self.rowMajor = rowMajor

        def __iter__ (self):
            return self

        def __next__(self):
        
            row = self.currentRow
            col = self.currentCol
            if self.rowMajor == 0:
                if self.currentCol >= self.cols:
                    raise StopIteration
                    
                self.currentRow = self.currentRow + 1
                inc = self.inner_stride
                if self.currentRow >= self.rows:
                    self.currentRow = 0
                    self.currentCol = self.currentCol + 1
                    inc = self.outer_stride
            else:
                if self.currentRow >= self.rows:
                    raise StopIteration
                    
                self.currentCol = self.currentCol + 1
                inc = self.inter_stride
                if self.currentCol >= self.cols:
                    self.currentCol = 0
                    self.currentRow = self.currentRow + 1
                    inc = self.outer_stride
                

            item = self.dataPtr.dereference()
            self.dataPtr = self.dataPtr + inc
            if (self.cols == 1): #if it's a column vector
                return ('[%d]' % (row,), item)
            elif (self.rows == 1): #if it's a row vector
                return ('[%d]' % (col,), item)
            return ('[%d,%d]' % (row, col), item)

    def children(self):
        return self._iterator(self.rows, self.cols, self.outer_stride, self.inner_stride, self.data, self.rowMajor)

    def to_string(self):
        return "Eigen::%s<%s,%d,%d,%s> (data ptr: %s)" % (self.variety, self.referenced, self.rows, self.cols, "RowMajor" if self.rowMajor else  "ColMajor", self.data)

class EigenQuaternionPrinter:
    "Print an Eigen Quaternion"

    def __init__(self, val):
        "Extract all the necessary information"
        # The gdb extension does not support value template arguments - need to extract them by hand
        type = val.type
        if type.code == gdb.TYPE_CODE_REF:
            type = type.target()
        self.type = type.unqualified().strip_typedefs()
        self.innerType = self.type.template_argument(0)
        self.val = val
        
        # Quaternions have a struct as their storage, so we need to walk through this
        self.data = self.val['m_coeffs']['m_storage']['m_data']['array']
        self.data = self.data.cast(self.innerType.pointer())
            
    class _iterator(Iterator):
        def __init__ (self, dataPtr):
            self.dataPtr = dataPtr
            self.currentElement = 0
            self.elementNames = ['x', 'y', 'z', 'w']

        def __iter__ (self):
            return self

        def __next__(self):
            element = self.currentElement

            if self.currentElement >= 4: #there are 4 elements in a quanternion
                raise StopIteration
            
            self.currentElement = self.currentElement + 1

            item = self.dataPtr.dereference()
            self.dataPtr = self.dataPtr + 1
            return ('[%s]' % (self.elementNames[element],), item)
            
    def children(self):
        
        return self._iterator(self.data)

    def to_string(self):
        return "Eigen::Quaternion<%s> (data ptr: %s)" % (self.innerType, self.data)

def build_eigen_dictionary ():
    pretty_printers_dict[re.compile('^Eigen::Quaternion<.*>$')] = lambda val: EigenQuaternionPrinter(val)
    pretty_printers_dict[re.compile('^Eigen::Ref<.*>$')] = lambda val: EigenRefPrinter("Ref", val)
    pretty_printers_dict[re.compile('^Eigen::Matrix<.*>$')] = lambda val: EigenMatrixPrinter("Matrix", val)
    pretty_printers_dict[re.compile('^Eigen::Array<.*>$')]  = lambda val: EigenMatrixPrinter("Array",  val)

def register_eigen_printers(obj):
    "Register eigen pretty-printers with objfile Obj"

    if obj == None:
        obj = gdb
    obj.pretty_printers.append(lookup_function)

def lookup_function(val):
    "Look-up and return a pretty-printer that can print va."

    type = val.type

    if type.code == gdb.TYPE_CODE_REF:
        type = type.target()
    
    type = type.unqualified().strip_typedefs()

    typename = type.tag
    if typename == None:
        return None

    for function in pretty_printers_dict:
        if function.search(typename):
            return pretty_printers_dict[function](val)

    return None

pretty_printers_dict = {}

build_eigen_dictionary ()
