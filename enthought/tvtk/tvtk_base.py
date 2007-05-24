"""Commonly used code by tvtk objects.

"""
# Author: Prabhu Ramachandran <prabhu_r@users.sf.net>
# Copyright (c) 2004-2007,  Enthought, Inc.
# License: BSD Style.

import types
import sys
import weakref

import vtk

from enthought.traits import api as traits
from enthought.traits.ui.api import BooleanEditor, RGBColorEditor, FileEditor
import messenger

######################################################################
# The TVTK object cache.
######################################################################

# The TVTK object cache (`_object_cache`).  This caches all the TVTK
# instances using weakrefs.  When a VTK object is wrapped via the
# `wrap_vtk` function this cache is checked.  The key is the VTK
# object's address.  The value of the dict is the TVTK wrapper object.
# If the VTK object address exists in the cache, it is returned by
# `wrap_vtk`.  `wrap_vtk` is defined in `tvtk_helper.py` which is
# stored in the ZIP file.

_dummy = None
# This makes the cache work even when the module is reloaded.
for name in ['tvtk_base', 'enthought.tvtk.tvtk_base']:
    if sys.modules.has_key(name):
        mod = sys.modules[name]
        if hasattr(mod, '_object_cache'):
            _dummy = mod._object_cache
        del mod
        break

if _dummy:
    _object_cache = _dummy
else:
    _object_cache = weakref.WeakValueDictionary()
del _dummy



######################################################################
# Special traits used by the tvtk objects.
######################################################################

true_bool_trait = traits.Trait('true',
                               {'true':  1, 't': 1, 'yes': 1,
                                'y': 1, 'on': 1, 1: 1, 'false': 0,
                                'f': 0, 'no':  0, 'n': 0,
                                'off': 0, 0: 0},
                               editor=BooleanEditor)

false_bool_trait = traits.Trait('false', true_bool_trait)


class TraitRevPrefixMap(traits.TraitPrefixMap):
    """A reverse mapped TraitPrefixMap.  This handler allows for
    something like the following::

      >>> class A(HasTraits):
      ...     a = Trait('ab', TraitRevPrefixMap({'ab':1, 'cd':2}))
      ...
      >>> a = A()
      >>> a.a = 'c'
      >>> print a.a
      'cd'
      >>> a.a = 1
      >>> print a.a
      'ab'

    That is, you can set the trait to the value itself.  If multiple
    keys map to the same value, one of the valid keys will be used.

    """    
    def __init__(self, map):
        traits.TraitPrefixMap.__init__(self, map)
        self._rmap = {}
        for key, value in map.items():
            self._rmap[value] = key

    def validate(self, object, name, value):
        try:
            if self._rmap.has_key(value):
                value = self._rmap[value]            
            if not self._map.has_key( value ):
                match = None
                n     = len( value )
                for key in self.map.keys():
                    if value == key[:n]:
                        if match is not None:
                           match = None
                           break
                        match = key
                if match is None:
                    self.error( object, name, self.repr( value ) )
                self._map[ value ] = match
            return self._map[ value ]
        except:
            self.error( object, name, self.repr( value ) )
        
    def info(self):
        keys = [repr(x) for x in self._rmap.keys()]
        keys.sort()
        msg = ' or '.join(keys)
        return traits.TraitPrefixMap.info(self) + ' or ' + msg


def vtk_color_trait(default, **metadata):
    Range = traits.Range
    if default[0] == -1.0:
        # Occurs for the vtkTextProperty's color trait.  Need to work
        # around.
        return traits.Trait(default, traits.Tuple(*default),
                            traits.Tuple(Range(0.0, 1.0),
                                         Range(0.0, 1.0),
                                         Range(0.0, 1.0),
                                         editor=RGBColorEditor),
                            **metadata)
    else:
        return traits.Trait(traits.Tuple(Range(0.0, 1.0, default[0]),
                                         Range(0.0, 1.0, default[1]),
                                         Range(0.0, 1.0, default[2])),
                            editor=RGBColorEditor, **metadata)


# Special cases for the FileName and FilePrefix
vtk_file_name = traits.Trait(None, None, traits.Str, types.UnicodeType,
                             editor=FileEditor)
vtk_file_prefix = traits.Trait(None, None, traits.Str, types.UnicodeType,
                               editor=(FileEditor, {'truncate_ext': True}))

# The Property class traits are delegated in the Actors.
vtk_property_delegate = traits.Delegate('property', modify=True)


######################################################################
# Utility functions.
######################################################################
def deref_vtk(obj):
    """Dereferences the VTK object from the object if possible."""
    if isinstance(obj, TVTKBase):
        return obj._vtk_obj
    else:
        return obj


######################################################################
# 'TVTKBase' class (base class for all tvtk classes):
######################################################################
class TVTKBase(traits.HasStrictTraits):
    """The base class for all TVTK objects.  This class encapsulates
    key functionality common to all the TVTK classes.

    TVTK classes provide a trait wrapped VTK object.  They also
    primitively picklable.  Only the basic state of the object itself
    is pickled.  References to other VTK objects are NOT pickled.
    
    """

    # This is just a dummy integer (MUST be > 1) that indicates that
    # we are updating the traits and there is no need to change the
    # underlying VTK object.
    DOING_UPDATE = 10

    ########################################
    # Private traits.

    # This trait is only used internally and should not activate any
    # notifications when set which is why we use `Python`.
    _in_set = traits.Python

    # A tuple of the observer IDs for the 'ModifiedEvent' and other
    # events.
    _observer_ids = traits.Tuple

    # The wrapped VTK object.
    _vtk_obj = traits.Trait(None, None, vtk.vtkObjectBase())

    # Stores the names of the traits that need to be updated.
    _updateable_traits_ = traits.Tuple


    #################################################################
    # `object` interface.
    #################################################################
    def __init__(self, klass, obj=None, update=True, **traits):
        """Object initialization.

        Parameters
        ----------

        - klass: `vtkObjectBase`

          A VTK class to wrap.  If `obj` is passed, its class must be
          the same as `klass` or a subclass of it.

        - obj: `vtkObjectBase` (default: None)

          An optional VTK object.  If passed the passed object is
          wrapped.  This defaults to `None` where a new VTK instance
          of class, `klass` is created.

        - update: `bool` (default: True)

          If True (default), the traits of the class are automatically
          updated based on the state of the wrapped VTK object.  If
          False, no updation is performed.  This is particularly
          useful when the object is being unpickled.

        - traits: `dict`

          A dictionary having the names of the traits as its keys.
          This allows a user to set the traits of the object while
          creating the object.

        """
        # Initialize the Python attribute.
        self._in_set = 0
        if obj:
            assert obj.IsA(klass.__name__)
            self._vtk_obj = obj
        else:
            self._vtk_obj = klass()

        #print "INIT", self.__class__.__name__, repr(self._vtk_obj)

        # Call the Super class to update the traits.
        # Inhibit any updates at this point since we update in the end
        # anyway.        
        self._in_set = 1
        super(TVTKBase, self).__init__(**traits)
        self._in_set = 0

        # Update the traits based on the values of the VTK object.
        if update:
            self.update_traits()

        # Setup the observer so the traits are updated even if the
        # wrapped VTK object changes.
        vtk_obj = self._vtk_obj
        messenger.connect(vtk_obj, 'ModifiedEvent',
                          self.update_traits)
        self._observer_ids += (vtk_obj.AddObserver('ModifiedEvent',
                                                   messenger.send),)
        _object_cache[vtk_obj.__this__] = self
    
    def __del__(self):
        #print "DEL", self.__class__.__name__, repr(self._vtk_obj)
        if hasattr(self, '_observer_ids') and self._observer_ids:
            for ob_id in self._observer_ids:
                try:
                    # The disconnection sometimes fails at exit.
                    self._vtk_obj.RemoveObserver(ob_id)
                except AttributeError:
                    pass
            try:
                messenger.disconnect(self._vtk_obj)
            except AttributeError:
                pass

    def __getinitargs__(self):
        """This is merely a placeholder so that subclasses can
        override this if needed.  This is called by `__setstate__`
        because `traits.HasTrait` is a newstyle class.        

        """
        # You usually don't want to call update when calling __init__
        # from __setstate__
        return (None, 0)

    def __getstate__(self):
        """Support for primitive pickling.  Only the basic state is
        pickled.
        """
        self.update_traits()
        d = self.__dict__.copy()
        for i in ['_vtk_obj', '_observer_ids', '_in_set', 'reference_count',
                  'global_warning_display', '__sync_trait__']:
            d.pop(i, None)
        return d

    def __setstate__(self, dict):
        """Support for primitive pickling.  Only the basic state is
        pickled.
        """        
        # This is a newstyle class so we need to call init here.
        if self._vtk_obj is None:
            self.__init__(*self.__getinitargs__())
        self._in_set = 1
        for i in dict:
            # Not enough to update the dict because the vtk object
            # needs to be updated.
            setattr(self, i, dict[i])
        self._in_set = 0

    def __str__(self):
        """Return a nice string representation of the object.

        This merely returns the result of str on the underlying VTK
        object.
        """
        return str(self._vtk_obj)
    
        
    #################################################################
    # `TVTKBase` interface.
    #################################################################

    def update_traits(self, obj=None, event=None):
        """Updates all the 'updateable' traits of the object.

        The method works by getting the current value from the wrapped
        VTK object.  `self._updateable_traits_` stores a tuple of
        tuples containing the trait name followed by the name of the
        get method to use on the wrapped VTK object.

        The `obj` and `event` parameters may be ignored and are not
        used in the function.  They exist only for compatibility with
        the VTK observer callback functions.
        
        """
        if self._in_set:
            return
        if not hasattr(self, '_updateable_traits_'):
            return

        self._in_set = self.DOING_UPDATE
        vtk_obj = self._vtk_obj
        
        # Save the warning state and turn it off!
        warn = vtk.vtkObject.GetGlobalWarningDisplay()
        vtk.vtkObject.GlobalWarningDisplayOff()

        for name, getter in self._updateable_traits_:
            try:
                val = getattr(vtk_obj, getter)()
            except (AttributeError, TypeError):
                pass
            else:
                if name == 'global_warning_display':
                    setattr(self, name, warn)
                else:
                    setattr(self, name, val)
        # Reset the warning state.
        vtk.vtkObject.SetGlobalWarningDisplay(warn)
        self._in_set = 0

    #################################################################
    # Non-public interface.
    #################################################################
    def _do_change(self, method, val, force_update=False):
        """This is called by the various traits when they change in
        order to update the underlying VTK object.

        Parameters
        ----------

        - method: `method`

          The method to invoke on the VTK object when called.

        - val: `Any`

          Argument to the method.

        - force_update: `bool` (default: False)

          If True, `update_traits` is always called at the end.
          
        """
        if self._in_set == self.DOING_UPDATE:
            return        
        vtk_obj = self._vtk_obj
        self._in_set += 1
        mtime = vtk_obj.GetMTime() + 1
        try:
            method(val)
        except TypeError:
            if hasattr(val, '__len__'):
                method(*val)
            else:
                raise
        self._in_set -= 1
        if force_update or vtk_obj.GetMTime() > mtime:
            self.update_traits()

    def _wrap_call(self, vtk_method, *args):
        """This method allows us to safely call a VTK method without
        calling `update_traits` during the call.  This method is
        therefore used to wrap any 'Set' call on a VTK object.

        The method returns the output of the vtk_method call.

        Parameters
        ----------

        - vtk_method: `method`

          The method to invoke safely.

        - args: `Any`

          Argument to be passed to the method.

        """
        vtk_obj = self._vtk_obj
        self._in_set += 1
        mtime = vtk_obj.GetMTime() + 1
        ret = vtk_method(*args)
        self._in_set -= 1
        if vtk_obj.GetMTime() > mtime:
            self.update_traits()
        return ret