# Licensed under an MIT open source license - see LICENSE

"""

SCOUSE - Semi-automated multi-COmponent Universal Spectral-line fitting Engine
Copyright (c) 2016-2018 Jonathan D. Henshaw
CONTACT: henshaw@mpia.de

"""

import numpy as np
from astropy.stats import median_absolute_deviation

from .base_spectrum import BaseSpectrum, get_rms

class saa(BaseSpectrum):

    def __init__(self, coords, flux, idx=None, scouse=None, sample=False):
        """
        Stores all the information regarding individual spectral averaging areas
        """

        super(saa, self).__init__(coords, flux, idx=idx, scouse=scouse)
        self._ytrim = trim_spectrum(self, scouse, flux)
        self._indices = None
        self._indiv_spectra = None
        self._sample = sample
        self._cube_shape = scouse.cube.shape

    @classmethod
    def from_indiv_spectrum(cls, indiv_spectrum, scouse, sample=False):
        return cls(coords=indiv_spectrum.coordinates,
                   flux=indiv_spectrum.flux,
                   scouse=scouse,
                   idx=indiv_spectrum.index,
                   sample=sample
                  )

    @property
    def ytrim(self):
        """
        Returns the spectrum of the spectral averaging area.
        """
        return self._ytrim

    @property
    def indices(self):
        """
        Returns the individual indices contained within the spectral
        averaging area.
        """
        return self._indices

    @property
    def indices_flat(self):
        """
        Returns the flattened individual indices contained within the spectral
        averaging area.
        """
        return np.ravel_multi_index(self.indices.T, self._cube_shape[1:])

    @property
    def to_be_fit(self):
        """
        Indicates whether or not the spectrum is to be fit (used for training
        set generation)
        """
        return self._sample

    @property
    def indiv_spectra(self):
        """
        Returns a dictionary containing the models to the individual spectra
        contained within the SAA
        """
        return self._indiv_spectra

    def __repr__(self):
        """
        Return a nice printable format for the object.
        """
        return "< scousepy Spectral Averaging Area SAA {0} >".format(self.index, self.coordinates)


def trim_spectrum(self, scouse, flux):
    """
    Trims a spectrum according to the user inputs
    """
    return flux[scouse.trimids]

def add_model(self, model):
    """
    Adds best-fitting model information to the SAA
    """
    self._model = model

def add_ids(self, ids):
    """
    Adds indices contained within the SAA
    """
    self._indices = np.array(ids, dtype='int')

def add_indiv_spectra(self, dict):
    """
    Adds indices contained within the SAA
    """
    self._indiv_spectra = dict

def merge_models(self, merge_spec):
    """
    Merges merge_spec models into self
    """
    main_models = self.models
    merge_models = merge_spec.models
    allmodels = []
    allmodels.append(main_models)
    allmodels.append(merge_models)
    self._models = [model for mergemods in allmodels for model in mergemods]

def clean_up(self):
    """
    Cleans model solutions
    """
    self._indiv_spectra = None
