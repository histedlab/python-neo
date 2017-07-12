# -*- coding: utf-8 -*-
"""
baserawio
======

Classes
-------

BaseRawIO
abstract class which should be overridden to write a RawIO.

RawIO is a new API in neo that is supposed to acces as fast as possible
raw data. All IO with theses carractéristics should/could be rewritten:
  * internally use of memmap (or hdf5)
  * reading header is quite cheap (not read all the file)
  * neo tree object is symetric and logical: same channel/units/event
    along all block and segments.
    


So this handle **only** one simplified but very frequent case of dataset:
    * Only one channel set  for AnalogSignal (aka ChannelIndex) stable along Segment
    * Only one channel set  for SpikeTrain (aka Unit) stable along Segment
    * AnalogSignal have all the same sampling_rate acroos all Segment
    * t_start/t_stop are the same for all object (AnalogSignal/SpikeTrain) inside a Segment
    

An helper class `neo.io.basefromrawio.BaseFromRaw` should transform a RawIO to
neo legacy IO from free.

With this API the IO have an attributes `header` with necessary keys.
See ExampleRawIO as example.




"""

from __future__ import unicode_literals, print_function, division, absolute_import

import logging
import numpy as np

from neo import logging_handler



possible_modes = ['one-file', 'multi-file', 'one-dir', 'multi-dir', 'url', 'other']

error_header = 'Header is not read yet, do parse_header() first'


_signal_channel_dtype = [
    ('name','U64'),
    #~ ('id','U64'),
    ('id','int64'),
    ('units','U64'),
    ('gain','float64'),
    ('offset','float64'),
]

_unit_channel_dtype = [
    ('name','U64'),
    ('id','U64'),
    #for waveform
    ('wf_units','U64'),
    ('wf_gain','float64'),
    ('wf_offset','float64'),
    ('wf_left_sweep','int64'),
    ('wf_sampling_rate','float64'),
]


_event_channel_dtype = [
        ('name','U64'),
        ('id','U64'),
        ('type', 'S5') , #epoch ot event
    ]


class BaseRawIO(object):
    """
    Generic class to handle.

    """
    
    name = 'BaseIO'
    description = ''
    extentions = []

    rawmode = None # one key in possible modes
    

    def __init__(self, **kargs):
        # create a logger for the IO class
        fullname = self.__class__.__module__ + '.' + self.__class__.__name__
        self.logger = logging.getLogger(fullname)
        # create a logger for 'neo' and add a handler to it if it doesn't
        # have one already.
        # (it will also not add one if the root logger has a handler)
        corename = self.__class__.__module__.split('.')[0]
        corelogger = logging.getLogger(corename)
        rootlogger = logging.getLogger()
        if not corelogger.handlers and not rootlogger.handlers:
            corelogger.addHandler(logging_handler)
        
        self.header = None
    
    def parse_header(self):
        """
        This must parse the file header to get all stuff for fast later one.
        
        This must contain
        self.header['signal_channels']
        
        """
        self._parse_header()
    
    def source_name(self):
        """Return fancy name of file source"""
        return self._source_name()
    
    def __repr__(self):
        txt = '{}: {}\n'.format(self.__class__.__name__, self.source_name())
        if self.header is not None:
            nb_block = self.block_count()
            txt += 'nb_block: {}\n'.format(nb_block)
            nb_seg = [self.segment_count(i) for i in range(nb_block)]
            txt += 'nb_segment:  {}\n'.format(nb_seg)
            
            for k in ('signal_channels', 'unit_channels'):
                ch = self.header[k]
                if len(ch)>8:
                    chantxt = "[{} ... {}]".format(', '.join(e for e in ch['name'][:4]),\
                                                                                ' '.join(e for e in ch['name'][-4:]))
                else:
                    chantxt = "[{}]".format(', '.join(e for e in ch['name']))
                txt += '{}: {}\n'.format(k, chantxt)
            
        return txt
        
    def _generate_empty_annotations(self):
        """
        Helper function that generate a nested dict
        of all annotations.
        must be called when theses are Ok:
          * block_count()
          * segment_count()
          * signal_channels_count()
          * unit_channels_count()
          * event_channels_count()
        
        Usage:
        raw_annotations['blocks'][block_index] = { 'nickname' : 'super block', 'segments' : ...}
        raw_annotations['blocks'][block_index] = { 'nickname' : 'super block', 'segments' : ...}
        raw_annotations['blocks'][block_index]['segments'][seg_index]['signals'][channel_index] = {'nickname': 'super channel'}
        raw_annotations['blocks'][block_index]['segments'][seg_index]['units'][unit_index] = {'nickname': 'super neuron'}
        raw_annotations['blocks'][block_index]['segments'][seg_index]['events'][ev_chan] = {'nickname': 'super trigger'}
        
        Theses annotations will be used at the neo.io API directly in objects.
        """
        signal_channels = self.header['signal_channels']
        unit_channels = self.header['unit_channels']
        event_channels = self.header['event_channels']
        
        a = {'blocks':[], 'signal_channels':[], 'unit_channels':[], 'event_channel':[]}
        for block_index in range(self.block_count()):
            d = {'segments':[]}
            d['file_origin'] = self.source_name()
            a['blocks'].append(d)
            for seg_index in range(self.segment_count(block_index)):
                d = {'signals':[], 'units' :[], 'events':[]}
                d['file_origin'] = self.source_name()
                a['blocks'][block_index]['segments'].append(d)
                
                for c in range(signal_channels.size):
                    #use for AnalogSignal.annotations
                    d = {}
                    d['name'] = signal_channels['name'][c]
                    d['channel_id'] = signal_channels['id'][c]
                    a['blocks'][block_index]['segments'][seg_index]['signals'].append(d)

                for c in range(unit_channels.size):
                    #use for SpikeTrain.annotations
                    d = {}
                    d['name'] = unit_channels['name'][c]
                    d['id'] = unit_channels['id'][c]
                    a['blocks'][block_index]['segments'][seg_index]['units'].append(d)

                for c in range(event_channels.size):
                    #use for Event.annotations
                    d = {}
                    d['name'] = event_channels['name'][c]
                    d['id'] = event_channels['id'][c]
                    a['blocks'][block_index]['segments'][seg_index]['events'].append(d)
        
        for c in range(signal_channels.size):
            #use for ChannelIndex.annotations
            d = {}
            d['name'] = signal_channels['name'][c]
            d['channel_id'] = signal_channels['id'][c]
            a['signal_channels'].append(d)

        for c in range(unit_channels.size):
            #use for Unit.annotations
            d = {}
            d['name'] = unit_channels['name'][c]
            d['id'] = unit_channels['id'][c]
            a['unit_channels'].append(d)

        for c in range(event_channels.size):
            #not used in neo.io at the moment could usefull one day
            d = {}
            d['name'] = event_channels['name'][c]
            d['id'] = event_channels['id'][c]
            a['event_channel'].append(d)
        
        self.raw_annotations = a
    
    def _repr_annotations(self):
        txt = 'Raw annotations\n'
        for block_index in range(self.block_count()):
            bl_a = self.raw_annotations['blocks'][block_index]
            txt += '*Block {}\n'.format(block_index)
            for k, v in bl_a.items():
                if k in ('segments', ): continue
                txt += '  -{}: {}\n'.format(k, v)
            for seg_index in range(self.segment_count(block_index)):
                seg_a = bl_a['segments'][seg_index]
                txt += '  *Segment {}\n'.format(seg_index)
                for k, v in seg_a.items():
                    if k in ('signals', 'units', 'events',  ): continue
                    txt += '    -{}: {}\n'.format(k, v)
                
                for child in ('signals', 'units', 'events'):
                    n = self.header[child[:-1]+'_channels'].shape[0]
                    for c in range(n):
                        neo_name = {'signals':'AnalogSignal', 
                                'units':'SpikeTrain', 'events':'Event/Epoch'}[child]
                        txt += '    *{} {}\n'.format(neo_name, c)
                        child_a = seg_a[child][c]
                        for k, v in child_a.items():
                            txt += '      -{}: {}\n'.format(k, v)
        
        return txt
    
    def print_annotations(self):
        """Print formated raw_annotations"""
        print(self._repr_annotations())
    

    def block_count(self):
        """return number of blocks"""
        return self._block_count()
    
    def segment_count(self, block_index):
        """return number of segment for a given block"""
        return self._segment_count(block_index)
        
    def signal_channels_count(self):
        """Return the number of signal channel.
        Same allong all block and Segment.
        """
        return len(self.header['signal_channels'])

    def unit_channels_count(self):
        """Return the number of unit (aka spike) channel.
        Same allong all block and Segment.
        """
        return len(self.header['unit_channels'])

    def event_channels_count(self):
        """Return the number of event/epoch channel.
        Same allong all block and Segment.
        """
        return len(self.header['event_channels'])

    def segment_t_start(self, block_index, seg_index):
        return self._segment_t_start(block_index, seg_index)

    def segment_t_stop(self, block_index, seg_index):
        return self._segment_t_stop(block_index, seg_index)
    
    ###
    # signal and channel zone
    def channel_name_to_index(self, channel_names):
        """
        Transform channel_names to channel_indexes.
        Based on self.header['signal_channels']
        """
        ch = self.header['signal_channels']
        channel_indexes,  = np.nonzero(np.in1d(ch['name'], channel_names))
        assert len(channel_indexes) == len(channel_names), 'not match'
        return channel_indexes
    
    def channel_id_to_index(self, channel_ids):
        """
        Transform channel_ids to channel_indexes.
        Based on self.header['signal_channels']
        """
        ch = self.header['signal_channels']
        channel_indexes,  = np.nonzero(np.in1d(ch['id'], channel_ids))
        assert len(channel_indexes) == len(channel_ids), 'not match'
        return channel_indexes

    def _get_channel_indexes(self, channel_indexes, channel_names, channel_ids):
        """
        select channel_indexes from channel_indexes/channel_names/channel_ids
        depending which is not None
        """
        if channel_indexes is None and channel_names is not None:
            channel_indexes = self.channel_name_to_index(channel_names)

        if channel_indexes is None and channel_ids is not None:
            channel_indexes = self.channel_id_to_index(channel_ids)
        
        return channel_indexes


    def analogsignal_shape(self, block_index, seg_index):
        """Return signals shape for a given block_index, seg_index"""
        return self._analogsignal_shape(block_index, seg_index)
    
    def analogsignal_sampling_rate(self):
        return self._analogsignal_sampling_rate()
    
    def get_analogsignal_chunk(self, block_index=0, seg_index=0, i_start=None, i_stop=None, 
                        channel_indexes=None, channel_names=None, channel_ids=None):
        """
        Return a chunk of raw signal.
        
        
        
        
        """
        channel_indexes = self._get_channel_indexes(channel_indexes, channel_names, channel_ids)
        
        raw_chunk = self._get_analogsignal_chunk(block_index, seg_index,  i_start, i_stop, channel_indexes)
        
        return raw_chunk

    def rescale_signal_raw_to_float(self, raw_signal,  dtype='float32',
                channel_indexes=None, channel_names=None, channel_ids=None):
        
        channel_indexes = self._get_channel_indexes(channel_indexes, channel_names, channel_ids)
        if channel_indexes is None:
            channel_indexes = slice(None)
        
        channels = self.header['signal_channels'][channel_indexes]
        
        float_signal = raw_signal.astype(dtype)
        
        if np.any(channels['gain'] !=1.):
            float_signal *= channels['gain']
        
        if np.any(channels['offset'] !=0.):
            float_signal += channels['offset']
        
        return float_signal
    
    # spiketrain and unit zone
    def spike_count(self,  block_index=0, seg_index=0, unit_index=0):
        return self._spike_count(block_index, seg_index, unit_index)
    
    def spike_timestamps(self,  block_index=0, seg_index=0, unit_index=0,
                        t_start=None, t_stop=None):
        """
        The timestamp is as close to the format itself. Sometimes float/int32/int64.
        Sometimes it is the index on the signal but not always.
        The conversion to second or index_on_signal is done outside here.
        
        t_start/t_sop are limits in seconds.
        
        """
        timestamp = self._spike_timestamps(block_index, seg_index, unit_index, t_start, t_stop)
        return timestamp
    
    def rescale_spike_timestamp(self, spike_timestamps, dtype='float64'):
        """
        Rescale spike timestamps to second
        """
        return self._rescale_spike_timestamp(spike_timestamps, dtype)
    
    # spiketrain waveform zone
    def spike_raw_waveforms(self,  block_index=0, seg_index=0, unit_index=0,
                        t_start=None, t_stop=None):
        wf = self._spike_raw_waveforms(block_index, seg_index, unit_index, t_start, t_stop)
        return wf
    
    
    def rescale_waveforms_to_float(self, raw_waveforms, dtype='float32', unit_index=0):
        wf_gain = self.header['unit_channels']['wf_gain'][unit_index]
        wf_offset = self.header['unit_channels']['wf_offset'][unit_index]
        
        float_waveforms = raw_waveforms.astype(dtype)
        
        float_waveforms *= wf_gain
        float_waveforms += wf_offset
        
        return float_waveforms

        
    # event and epoch zone
    def event_count(self,  block_index=0, seg_index=0, event_channel_index=0):
        return self._event_count(block_index, seg_index, event_channel_index)

    def event_timestamps(self,  block_index=0, seg_index=0, event_channel_index=0,
                        t_start=None, t_stop=None):
        """
        The timestamp is as close to the format itself. Sometimes float/int32/int64.
        Sometimes it is the index on the signal but not always.
        The conversion to second or index_on_signal is done outside here.
        
        t_start/t_sop are limits in seconds.
        
        returns
            timestamp
            labels
            durations

        """
        timestamp, durations, labels = self._event_timestamps(block_index, seg_index, event_channel_index, t_start, t_stop)
        return timestamp, durations, labels
    
    def rescale_event_timestamp(self, event_timestamps, dtype='float64'):
        """
        Rescale event timestamps to s
        """
        return self._rescale_event_timestamp(event_timestamps, dtype)
    
    def rescale_epoch_duration(self, raw_duration, dtype='float64'):
        """
        Rescale epoch raw duration to s
        """
        return self._rescale_epoch_duration(raw_duration, dtype)  
    

    ##################
    
    # Functions to be implement in IO below here
    
    def _parse_header(self):
        raise(NotImplementedError)
        #must call 
        #self._generate_empty_annotations()
    
    def _source_name(self):
        raise(NotImplementedError)
    
    def _block_count(self):
        raise(NotImplementedError)
    
    def _segment_count(self, block_index):
        raise(NotImplementedError)
    
    def _segment_t_start(self, block_index, seg_index):
        raise(NotImplementedError)

    def _segment_t_stop(self, block_index, seg_index):
        raise(NotImplementedError)
    
    ###
    # signal and channel zone
    def _analogsignal_shape(self, block_index, seg_index):
        raise(NotImplementedError)
        
    def _analogsignal_sampling_rate(self):
        raise(NotImplementedError)

    def _get_analogsignal_chunk(self, block_index, seg_index,  i_start, i_stop, channel_indexes):
        raise(NotImplementedError)
    
    ###
    # spiketrain and unit zone
    def _spike_count(self,  block_index, seg_index, unit_index):
        raise(NotImplementedError)
    
    def _spike_timestamps(self,  block_index, seg_index, unit_index, t_start, t_stop):
        raise(NotImplementedError)
    
    def _rescale_spike_timestamp(self, spike_timestamps, dtype):
        raise(NotImplementedError)

    ###
    # spike waveforms zone
    def _spike_raw_waveforms(self, block_index, seg_index, unit_index, t_start, t_stop):
        raise(NotImplementedError)
    
    ###
    # event and epoch zone
    def _event_count(self, block_index, seg_index, event_channel_index):
        raise(NotImplementedError)
    
    def _event_timestamps(self,  block_index, seg_index, event_channel_index, t_start, t_stop):
        raise(NotImplementedError)
    
    def _rescale_event_timestamp(self, event_timestamps, dtype):
        raise(NotImplementedError)
    
    def _rescale_epoch_duration(self, raw_duration, dtype):
        raise(NotImplementedError)

