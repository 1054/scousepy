# Licensed under an MIT open source license - see LICENSE

"""

SCOUSE - Semi-automated multi-COmponent Universal Spectral-line fitting Engine
Copyright (c) 2016-2018 Jonathan D. Henshaw
CONTACT: henshaw@mpia.de

"""

import numpy as np
import sys
from .parallel_map import *

def initialise_fitting(scouseobject):
    """
    Initialising the autonomous decomposition. Here scouse creates the
    individual spectra using the information in each SAA.

    Parameters
    ----------
    scouseobject : Instance of the scousepy class
    indivspec_list : list
        A list which will house all of the individual spectra generated by
        scouse

    Returns
    -------
        A list of all spectra to be fit

    """
    from .model_housing2 import individual_spectrum
    from .verbose_output import print_to_terminal
    import time

    if scouseobject.verbose:
        progress_bar = print_to_terminal(stage='s3', step='init',length=scouseobject.lenspec)

    # create the list that will contain all of the spectra
    indivspec_list=[]
    # generate a template spectrum for the fitter
    template=gen_template(scouseobject)

    # begin by looping through the SAA dictionaries
    for i in range(len(scouseobject.wsaa)):
        saa_dict=scouseobject.saa_dict[i]

        # loop over the items in the dictionary
        for j, SAA in saa_dict.items():
            # determine whether the SAA is to be fit or not
            if SAA.to_be_fit:
                # get the indices of the pixels contained within the SAA
                indices=SAA.indices
                indices_flat=SAA.indices_flat

                # loop over these and for each one create an instance of the
                # individual_spectrum class
                for k in range(len(indices_flat)):
                    # parameters for the individual_spectrum class
                    index=indices_flat[k]
                    coordinates=np.array([indices[k,1],indices[k,0]])
                    spectrum=scouseobject.cube[:,indices[k,0],indices[k,1]].value
                    # create the spectrum
                    indivspec=individual_spectrum(coordinates,spectrum,index=index,
                                        scouseobject=scouseobject, saa_dict_index=i,
                                        saaindex=SAA.index)

                    # add the template
                    setattr(indivspec, 'template', template)
                    setattr(indivspec, 'guesses_from_parent', SAA.model.params)
                    # append the model to the list
                    indivspec_list.append(indivspec)
                    if scouseobject.verbose:
                        progress_bar.update()

    if scouseobject.verbose:
        progress_bar.close()

    return indivspec_list

def gen_template(scouseobject):
    """
    Here we create a template spectrum. Parallelised fitting replaces the
    spectrum in memory and so it is best to generate a template outside of the
    parallel fitting process.

    Parameters
    ----------
    scouseobject : instance of the scousepy class
    SAA : instance of the saa class

    Returns
    -------
        pyspeckit spectrum

    """
    import astropy.units as u
    from .SpectralDecomposer import Decomposer

    # properties of the template spectrum
    unit=scouseobject.cube.header['BUNIT'],
    xarrkwargs={'unit':'km/s',
                'refX': scouseobject.cube.wcs.wcs.restfrq*u.Hz,
                'velocity_convention': 'radio',}
    spectral_axis=scouseobject.xtrim
    decomposer=Decomposer(spectral_axis, np.ones_like(spectral_axis), 0.0)
    Decomposer.create_a_template(decomposer,unit=unit,xarrkwargs=xarrkwargs)

    return decomposer.psktemplate

def autonomous_decomposition(scouseobject, indivspec_list):
    """
    autonomous decomposition of the spectra. Reads in a list of spectra and
    uses pyspeckit to fit the data using guesses from the parent SAA

    Parameters
    ----------
    scouseobject : instance of the scousepy class
    indivspec_list : list
        A list which will house all of the individual spectra generated by
        scouse

    Returns
    -------
        list of modelled spectra

    """
    from tqdm import tqdm
    from .model_housing2 import individual_spectrum
    from .verbose_output import print_to_terminal

    indivspec_list_completed=[]

    if scouseobject.verbose:
        progress_bar = print_to_terminal(stage='s3', step='fitinit')

    scouseobjectlist=[scouseobject.xtrim,scouseobject.trimids,scouseobject.fittype,
                      scouseobject.tol,scouseobject.cube.header['CDELT3']]

    # loop over the list of spectra removing elements along the way as they
    # are successfully modelled.
    while np.size(np.asarray(indivspec_list) != 0.0):
        inputlist=[scouseobjectlist+[indivspec] for indivspec in indivspec_list]

        # if njobs > 1 run in parallel else in series
        if scouseobject.njobs > 1:
            results = parallel_map(decomposition_method, inputlist, numcores=scouseobject.njobs)
        else:
            if scouseobject.verbose:
                results=[decomposition_method(input) for input in tqdm(inputlist)]
            else:
                results=[decomposition_method(input) for input in inputlist]

        # now add model solutions to the relevant spectra and add completed
        # spectra to an output list
        for i, result in enumerate(results):
            model=result[0]
            guesses_updated=result[1]
            indivspec=indivspec_list[i]
            # remove the template
            setattr(indivspec,'template',None)

            if model is None:
                if np.size(guesses_updated) == 0.0:
                    # if the guesses reduces to zero then we consider the
                    # modelling complete as the fit has failed. So update the
                    # completed list.
                    indivspec_list_completed.append(indivspec)
                    indivspec_list[i]=None
                else:
                    # if the model is none but the number of guesses is not zero
                    # then we will try fit this spectrum again with some new
                    # initial guesses.
                    setattr(indivspec,'guesses_updated',guesses_updated,)
            else:
                # if a model has been found - update the completed list
                individual_spectrum.add_model(indivspec, model)
                indivspec_list_completed.append(indivspec)
                indivspec_list[i]=None

        indivspec_list = [indivspec for indivspec in indivspec_list if indivspec != None]

    return indivspec_list_completed

def decomposition_method(input):
    """
    Decomposition of an individual spectrum using input guesses from the parent
    SAA

    Parameters
    ----------
    input : list
        A list which contains the following:

        spectral_axis : an array of the spectral axis
        specids : a mask over which the spectrum will be fitted
        fittype : the type of fit scouse will attempt to perform
        tol : the tolerance values for comparison with the parent saa spectrum
        res : the channel spacing of the data
        indivspec : an instance of the individual_spectrum class

    Returns
    -------
        A list containing the model and the updated guesses

    """
    from .SpectralDecomposer import Decomposer
    from .model_housing2 import indivmodel

    # unpack the inputs
    spectral_axis,specids,fittype,tol,res,indivspec = input
    spectrum=indivspec.spectrum[specids]
    rms=indivspec.rms

    # set up the decomposer
    decomposer=Decomposer(spectral_axis,spectrum,rms)
    setattr(decomposer,'psktemplate',indivspec.template,)

    # inputs to initiate the fitter
    if np.size(indivspec.guesses_updated)<=1:
        guesses=indivspec.guesses_from_parent
    else:
        guesses=indivspec.guesses_updated

    # always pass the parent SAA parameters for comparison
    guesses_parent=indivspec.guesses_from_parent
    # fit the spectrum
    Decomposer.fit_spectrum_from_parent(decomposer,guesses,guesses_parent,tol,res,fittype=fittype,)
    # # generate a model
    if decomposer.validfit:
        model=indivmodel(decomposer.modeldict)
    else:
        model=None

    return [model,decomposer.guesses_updated]

def compile_spectra(scouseobject, indivspec_list_completed):
    """
    Because there are multiple SAAs, at this point there are potentially
    multiple solutions to individual spectra. Here we compile all solutions
    to an individual spectrum, removing any duplicate solutions, and
    wrap them up to a single instance of the individual_spectrum class. These
    are then sorted and then packaged in a dictionary.

    Parameters
    ----------
    scouseobject : instance of the scousepy class
    indivspec_list : list
        A list containing the modelled spectra

    Returns
    -------
        A dictionary of modelled spectra
    """
    from tqdm import tqdm
    from .verbose_output import print_to_terminal

    if scouseobject.verbose:
        progress_bar = print_to_terminal(stage='s3', step='compileinit')

    # start by getting all of the indices
    indexarr=np.asarray([indivspec.index for indivspec in indivspec_list_completed])
    # get the unique ones
    indexarr_unique=np.sort(np.unique(indexarr))

    # create a list to house the output
    indivspec_list_compiled=[]
    # loop over the individual spectra
    inputlist=[[i]+[indexarr]+[indexarr_unique]+[indivspec_list_completed] for i in range(len(indexarr_unique))]

    if scouseobject.verbose:
        results=[compilation_method(input) for input in tqdm(inputlist)]
    else:
        results=[compilation_method(input) for input in inputlist]

    # create a dictionary that is going to contain all of our models
    scouseobject.indiv_dict={}
    for i, indivspec in enumerate(results):
        key=indivspec.index
        scouseobject.indiv_dict[key]=indivspec

def compilation_method(input):
    """
    Method used to compile the spectra

    Parameters
    ----------
    input : list
        A list which contains the following:

        i : indexing the fitting
        indexarr : list of all indices contained in indivspec_list_completed
        indexarr_unique : unique indices in indivspec_list_completed
        indivspec_list_completed : the list of modelled spectra

    Returns
    -------
    indivspec : an instance of the individual_spectrum class
        This has been modified such that a single spectrum contains multiple
        models if they are available

    """
    # unpack the input
    i, indexarr, indexarr_unique, indivspec_list_completed = input
    # identify the locations of the modelled spectra
    idx=np.where(indexarr==indexarr_unique[i])[0]

    # if the size of idx is 1 there are two possibilities:
    #   1. the model_from_parent has a none value
    #   2. there is only one available model
    # here we add both
    if np.size(idx)==1:
        # get the spectrum
        indivspec=indivspec_list_completed[idx[0]]
        # create a list of models and saa pointers for the unique values
        saa_dict_index=[indivspec.saa_dict_index]
        saaindex=[indivspec.saaindex]
        model_from_parent=[indivspec.model_from_parent]
        # add the information to this spectrum
        setattr(indivspec, 'saa_dict_index', saa_dict_index)
        setattr(indivspec, 'saaindex', saaindex)
        setattr(indivspec, 'model_from_parent', model_from_parent)
    else:
        # else there are multiple models available for a given solution

        # create a sublist of modelled spectra
        indivspec_sublist_completed=[indivspec_list_completed[j] for j in idx]
        # get the aic values for which we will determine uniqueness
        aic_sublist_completed=[np.around(indivspec.model_from_parent.AIC, decimals=2) if indivspec.model_from_parent is not None else np.nan for indivspec in indivspec_sublist_completed]

        # convert to arrays
        aic_subarr_completed=np.asarray(aic_sublist_completed)
        indivspec_subarr_completed = np.asarray(indivspec_sublist_completed)
        # if in all cases the spectrum could not be fit and therefore
        # model_from_parent==None in all cases just take the first and
        # update
        if not np.any(~np.isnan(aic_subarr_completed)):
            # select the first model from the list
            indivspec=indivspec_subarr_completed[0]
            # create a list of models and saa pointers for the unique values
            saa_dict_index=[indivspec.saa_dict_index]
            saaindex=[indivspec.saaindex]
            model_from_parent=[indivspec.model_from_parent]
            # add the information to this spectrum
            setattr(indivspec, 'saa_dict_index', saa_dict_index)
            setattr(indivspec, 'saaindex', saaindex)
            setattr(indivspec, 'model_from_parent', model_from_parent)

        else:
            # find the unique (non-nan) aic values
            uniqvals, uniqids = np.unique(aic_subarr_completed[~np.isnan(aic_subarr_completed)], return_index=True)

            # create a list of models and saa pointers for the unique values
            saa_dict_index=[indivspec.saa_dict_index for indivspec in indivspec_subarr_completed[uniqids]]
            saaindex=[indivspec.saaindex for indivspec in indivspec_subarr_completed[uniqids]]
            model_from_parent=[indivspec.model_from_parent for indivspec in indivspec_subarr_completed[uniqids]]

            # select the first model from the list
            indivspec=indivspec_subarr_completed[uniqids[0]]
            # add the information to this
            setattr(indivspec, 'saa_dict_index', saa_dict_index)
            setattr(indivspec, 'saaindex', saaindex)
            setattr(indivspec, 'model_from_parent', model_from_parent)

    return indivspec
