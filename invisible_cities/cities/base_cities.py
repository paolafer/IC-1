"""
This module defines base classes for the IC cities. The classes are:
City: Handles input and output files, compression, and access to data base
DeconvolutionCity: A City that performs deconvolution of the PMT RWFs
CalibratedCity: A DeconvolutionCity that perform the calibrated sum of the
                PMTs and computes the calibrated signals in the SiPM plane.
PmapCity: A CalibratedCity that computes S1, S2 and S2Si that togehter
          constitute a PMAP.

Authors: J.J. Gomez-Cadenas and J. Generowicz.
Feburary, 2017.
"""

from collections import namedtuple
import numpy as np

from   invisible_cities.database import load_db
from   invisible_cities.core.system_of_units_c import SystemOfUnits
import invisible_cities.sierpe.blr as blr
import invisible_cities.core.peak_functions_c as cpf
import invisible_cities.core.pmaps_functions as pmp

units = SystemOfUnits()
S12Params = namedtuple('S12Params', 'tmin tmax stride lmin lmax rebin')


class City:
    """Base class for all cities.
       An IC city consumes data stored in the input_files and produce new data
       which is stored in the output_file. In addition to setting input and
       output files, the base class sets the print frequency and accesses
       the data base, storing as attributed several calibration coefficients

     """

    def __init__(self,
                 run_number  = 0,
                 files_in    = None,
                 file_out    = None,
                 compression = 'ZLIB4',
                 nprint      = 10000):

        self.run_number     = run_number
        self.nprint         = nprint  # default print frequency
        self.input_files    = files_in
        self.output_file    = file_out
        self.compression    = compression
        # access data base
        DataPMT             = load_db.DataPMT (run_number)
        DataSiPM            = load_db.DataSiPM(run_number)

        # This is JCK-1: text reveals symmetry!
        self.xs              = DataSiPM.X.values
        self.ys              = DataSiPM.Y.values
        self.adc_to_pes      = abs(DataPMT.adc_to_pes.values).astype(np.double)
        self.sipm_adc_to_pes = DataSiPM.adc_to_pes.values    .astype(np.double)
        self.coeff_c         = DataPMT.coeff_c.values        .astype(np.double)
        self.coeff_blr       = DataPMT.coeff_blr.values      .astype(np.double)
        self.noise_rms       = DataPMT.noise_rms.values      .astype(np.double)

    @property
    def monte_carlo(self):
        return self.run_number <= 0

    def set_print(self, nprint=1000):
        """Print frequency."""
        self.nprint = nprint

    def set_input_files(self, input_files):
        """Set the input files."""
        self.input_files = input_files

    def set_output_file(self, output_file):
        """Set the input files."""
        self.output_file = output_file

    def set_compression(self, compression):
        """Set the input files."""
        self.compression = compression


class DeconvolutionCity(City):
    """A Deconvolution city extends the City base class adding the
       deconvolution step, which transforms RWF into CWF.
       The parameters of the deconvolution are the number of samples
       used to compute the baseline (n_baseline) and the threshold to
       thr_trigger in the rising signal (thr_trigger)
    """

    def __init__(self,
                 run_number  = 0,
                 files_in    = None,
                 file_out    = None,
                 compression = 'ZLIB4',
                 nprint      = 10000,
                 n_baseline  = 28000,
                 thr_trigger = 5 * units.adc):

        City.__init__(self,
                      run_number  = run_number,
                      files_in    = files_in,
                      file_out    = file_out,
                      compression = compression,
                      nprint      = nprint)
        # BLR parameters
        self.n_baseline  = n_baseline
        self.thr_trigger = thr_trigger

    def set_blr(self, n_baseline, thr_trigger):
        """Set the parameters of the Base Line Restoration (BLR)"""
        self.n_baseline  = n_baseline
        self.thr_trigger = thr_trigger

    def deconv_pmt(self, RWF):
        """Deconvolve the RWF of the PMTs"""
        return blr.deconv_pmt(RWF,
                              self.coeff_c,
                              self.coeff_blr,
                              n_baseline  = self.n_baseline,
                              thr_trigger = self.thr_trigger)


class CalibratedCity(DeconvolutionCity):
    """A calibrated city extends a DeconvCity, performing two actions.
       1. Compute the calibrated sum of PMTs, in two flavours:
          a) csum: PMTs waveforms are equalized to photoelectrons (pes) and
             added
          b) csum_mau: waveforms are equalized to photoelectrons;
              compute a MAU that follows baseline and add PMT samples above
              MAU + threshold
       2. Compute the calibrated signal in the SiPMs:
          a) equalize to pes;
          b) compute a MAU that follows baseline and keep samples above
             MAU + threshold.
       """

    def __init__(self,
                 run_number  = 0,
                 files_in    = None,
                 file_out    = None,
                 compression = 'ZLIB4',
                 nprint      = 10000,
                 n_baseline  = 28000,
                 thr_trigger = 5 * units.adc,
                 n_MAU       = 100,
                 thr_MAU     = 3.0*units.adc,
                 thr_csum_s1 = 0.2*units.adc,
                 thr_csum_s2 = 1.0*units.adc,
                 n_MAU_sipm  = 100,
                 thr_sipm    = 5.0*units.pes):

        DeconvolutionCity.__init__(self,
                                   run_number  = run_number,
                                   files_in    = files_in,
                                   file_out    = file_out,
                                   compression = compression,
                                   nprint      = nprint,
                                   n_baseline  = n_baseline,
                                   thr_trigger = thr_trigger)

        # Parameters of the PMT csum.
        self.n_MAU       = n_MAU
        self.thr_MAU     = thr_MAU
        self.thr_csum_s1 = thr_csum_s1
        self.thr_csum_s2 = thr_csum_s2

        # Parameters of the SiPM signal
        self.n_MAU_sipm   = n_MAU_sipm
        self.thr_sipm = thr_sipm

    def set_csum(self, n_MAU, thr_MAU, thr_csum_s1, thr_csum_s2):
        """Set CSUM parameters"""
        self.n_MAU       = n_MAU
        self.thr_MAU     = thr_MAU
        self.thr_csum_s1 = thr_csum_s1
        self.thr_csum_s2 = thr_csum_s2

    def set_sipm(self, n_MAU_sipm=100, thr_sipm=5 * units.pes):
        """Cutoff for SiPMs."""
        self.thr_sipm = thr_sipm
        self.n_MAU_sipm   = n_MAU_sipm

    def calibrated_pmt_sum(self, CWF):
        """Return the csum and csum_mau calibrated sums"""
        return cpf.calibrated_pmt_sum(CWF,
                                      self.adc_to_pes,
                                      n_MAU =   self.n_MAU,
                                      thr_MAU = self.thr_MAU)

    def csum_zs(self, csum, threshold):
        """Zero Suppression over csum"""
        return cpf.wfzs(csum, threshold=threshold)

    def calibrated_signal_sipm(self, SiRWF):
        """Return the calibrated signal in the SiPMs."""
        return cpf.signal_sipm(SiRWF,
                               self.sipm_adc_to_pes,
                               thr =   self.thr_sipm,
                               n_MAU = self.n_MAU_sipm)


class PmapCity(CalibratedCity):
    """A PMAP city extends a CalibratedCity, computing the S1, S2 and S2Si
       objects that togehter constitute a PMAP.

    """

    def __init__(self,
                 run_number  = 0,
                 files_in    = None,
                 file_out    = None,
                 compression = 'ZLIB4',
                 nprint      = 10000,
                 n_baseline  = 28000,
                 thr_trigger = 5 * units.adc,
                 n_MAU       = 100,
                 thr_MAU     = 3.0*units.adc,
                 thr_csum_s1 = 0.2*units.adc,
                 thr_csum_s2 = 1.0*units.adc,
                 n_MAU_sipm  = 100,
                 thr_sipm    = 5.0*units.pes,
                 s1_params   = None,
                 s2_params   = None,
                 thr_sipm_s2 = 30*units.pes):

        CalibratedCity.__init__(self,
                                run_number  = run_number,
                                files_in    = files_in,
                                file_out    = file_out,
                                compression = compression,
                                nprint      = nprint,
                                n_baseline  = n_baseline,
                                thr_trigger = thr_trigger,
                                n_MAU       = n_MAU,
                                thr_MAU     = thr_MAU,
                                thr_csum_s1 = thr_csum_s1,
                                thr_csum_s2 = thr_csum_s2,
                                n_MAU_sipm  = n_MAU_sipm,
                                thr_sipm    = thr_sipm)

        self.s1_params   = s1_params
        self.s2_params   = s2_params
        self.thr_sipm_s2 = thr_sipm_s2

    def set_pmap_params(self,
                        s1_params,
                        s2_params,
                        thr_sipm_s2 = 30*units.pes):
        """Parameters for PMAP searches."""
        self.s1_params = s1_params
        self.s2_params = s2_params
        self.thr_sipm_s2 = thr_sipm_s2

    def find_S12(self, s1_ene, s1_indx, s2_ene, s2_indx):
        """Return S1 and S2"""
        S1 = cpf.find_S12(s1_ene,
                          s1_indx,
                          **self.s1_params._asdict())

        S2 = cpf.find_S12(s2_ene,
                          s2_indx,
                          **self.s2_params._asdict())
        return S1, S2

    def find_S2Si(self, S2, sipmzs):
        """Return S2Si"""

        SIPM = cpf.select_sipm(sipmzs)
        S2Si = pmp.sipm_s2_dict(SIPM, S2, thr = self.thr_sipm_s2)
        return S2Si