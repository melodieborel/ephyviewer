# -*- coding: utf-8 -*-
"""
This module include some facilities to make data source from:
  * neo.rawio so on disk sources (signals, spikes, epoch...)
  * neo objects in memory (neo.AnalogSignal, neo.Epoch, neo.SpikeTrain)

"""

from .sourcebase import BaseDataSource
import sys
import logging

import numpy as np

try:
    from distutils.version import LooseVersion as V
    import neo
    if V(neo.__version__)>='0.6.0':
        HAVE_NEO = True
        from neo.rawio.baserawio import BaseRawIO
    else:
        HAVE_NEO = False
        #~ print('neo version is too old', neo.__version__)
except ImportError:
    HAVE_NEO = False

from .signals import BaseAnalogSignalSource, InMemoryAnalogSignalSource
from .spikes import BaseSpikeSource, InMemorySpikeSource
from .events import BaseEventAndEpoch, InMemoryEventSource
from .epochs import InMemoryEpochSource



logger = logging.getLogger()

#~ print('HAVE_NEO', HAVE_NEO)



## neo.core stuff

class NeoAnalogSignalSource(InMemoryAnalogSignalSource):
    def __init__(self, neo_sig):
        signals = neo_sig.magnitude
        sample_rate = float(neo_sig.sampling_rate.rescale('Hz').magnitude)
        t_start = float(neo_sig.t_start.rescale('s').magnitude)

        InMemoryAnalogSignalSource.__init__(self, signals, sample_rate, t_start, channel_names=None)


class NeoSpikeTrainSource(InMemorySpikeSource):
    def __init__(self, neo_spiketrains=[]):
        all_spikes = []
        for neo_spiketrain in neo_spiketrains:
            name = neo_spiketrain.name
            if name is None:
                name = ''
            all_spikes.append({'time' : neo_spiketrain.times.rescale('s').magnitude,
                                        'name' : name})
        InMemorySpikeSource.__init__(self, all_spikes=all_spikes)

class NeoEventSource(InMemoryEventSource):
    def __init__(self, neo_events=[]):
        all_events = []
        for neo_event in neo_events:
            all_events.append({
                'name': neo_event.name,
                'time': neo_event.times.rescale('s').magnitude,
                'label': np.array(neo_event.labels),
            })
        InMemoryEventSource.__init__(self, all_events = all_events)

class NeoEpochSource(InMemoryEpochSource):
    def __init__(self, neo_epochs=[]):
        all_epochs = []
        for neo_epoch in neo_epochs:
            all_epochs.append({
                'name': neo_epoch.name,
                'time': neo_epoch.times.rescale('s').magnitude,
                'duration': neo_epoch.durations.rescale('s').magnitude,
                'label': np.array(neo_epoch.labels),
            })
        epoch_source = InMemoryEpochSource.__init__(self, all_epochs = all_epochs)





def get_sources_from_neo_segment(neo_seg):
    assert HAVE_NEO
    assert isinstance(neo_seg, neo.Segment)

    sources = {'signal':[], 'epoch':[], 'spike':[],'event':[],}

    for neo_sig in neo_seg.analogsignals:
        # normally neo signals are grouped by same sampling rate in one AnalogSignal
        # with shape (nb_channel, nb_sample)
        sources['signal'].append(NeoAnalogSignalSource(neo_sig))

    sources['spike'].append(NeoSpikeTrainSource(neo_seg.spiketrains))
    sources['event'].append(NeoEventSource(neo_seg.events))
    sources['epoch'].append(NeoEpochSource(neo_seg.epochs))


    return sources





## neo.rawio stuff

# this can be remove when neo version 0.10 will be out
class AnalogSignalFromNeoRawIOSource_until_v9(BaseAnalogSignalSource):
    def __init__(self, neorawio, channel_indexes=None):

        BaseAnalogSignalSource.__init__(self)
        self.with_scatter = False

        self.neorawio =neorawio
        if channel_indexes is None:
            channel_indexes = slice(None)
        self.channel_indexes = channel_indexes
        self.channels = self.neorawio.header['signal_channels'][channel_indexes]
        self.sample_rate = self.neorawio.get_signal_sampling_rate(channel_indexes=self.channel_indexes)

        #TODO: something for multi segment
        self.block_index = 0
        self.seg_index = 0

    @property
    def nb_channel(self):
        return len(self.channels)

    def get_channel_name(self, chan=0):
        return self.channels[chan]['name']

    @property
    def t_start(self):
        t_start = self.neorawio.get_signal_t_start(self.block_index, self.seg_index,
                    channel_indexes=self.channel_indexes)
        return t_start

    @property
    def t_stop(self):
        t_stop = self.t_start + self.get_length()/self.sample_rate
        return t_stop

    def get_length(self):
        length = self.neorawio.get_signal_size(self.block_index, self.seg_index,
                        channel_indexes=self.channel_indexes)
        return length

    def get_gains(self):
        return self.neorawio.header['signal_channels']['gain'][self.channel_indexes]

    def get_offsets(self):
        return self.neorawio.header['signal_channels']['offset'][self.channel_indexes]

    def get_shape(self):
        return (self.get_length(), self.nb_channel)

    def get_chunk(self, i_start=None, i_stop=None):
        sigs = self.neorawio.get_analogsignal_chunk(block_index=self.block_index, seg_index=self.seg_index,
                        i_start=i_start, i_stop=i_stop, channel_indexes=self.channel_indexes)
        return sigs


# this fit the neo API >= 0.10 (with streams concept)
class AnalogSignalFromNeoRawIOSource(BaseAnalogSignalSource):
    def __init__(self, neorawio, stream_index, channel_indexes=None):

        BaseAnalogSignalSource.__init__(self)
        self.with_scatter = False

        self.neorawio =neorawio
        self.stream_index = stream_index
        if channel_indexes is None:
            channel_indexes = slice(None)
        self.channel_indexes = channel_indexes
        
        
        self.stream_id = self.neorawio.header['signal_streams'][stream_index]['id']
        signal_channels = self.neorawio.header['signal_channels']
        mask = signal_channels['stream_id'] == self.stream_id
        self.channels = signal_channels[mask][self.channel_indexes]

        self.sample_rate = self.neorawio.get_signal_sampling_rate(stream_index=self.stream_index)

        #TODO: something for multi segment
        self.block_index = 0
        self.seg_index = 0

    @property
    def nb_channel(self):
        return len(self.channels)

    def get_channel_name(self, chan=0):
        return self.channels[chan]['name']

    @property
    def t_start(self):
        t_start = self.neorawio.get_signal_t_start(self.block_index, self.seg_index,
                    stream_index=self.stream_index)
        return t_start

    @property
    def t_stop(self):
        t_stop = self.t_start + self.get_length()/self.sample_rate
        return t_stop

    def get_length(self):
        length = self.neorawio.get_signal_size(self.block_index, self.seg_index,
                        stream_index=self.stream_index)
        return length

    def get_gains(self):
        return  self.channels['gain']

    def get_offsets(self):
        return  self.channels['offset']

    def get_shape(self):
        return (self.get_length(), self.nb_channel)

    def get_chunk(self, i_start=None, i_stop=None):
        sigs = self.neorawio.get_analogsignal_chunk(block_index=self.block_index, seg_index=self.seg_index,
                        i_start=i_start, i_stop=i_stop, stream_index=self.stream_index, 
                        channel_indexes=self.channel_indexes)
        return sigs


# handle old neo API <0.10
class SpikeFromNeoRawIOSource_until_v9(BaseSpikeSource):
    def __init__(self, neorawio, channel_indexes=None):
        self.neorawio =neorawio
        if channel_indexes is None:
            channel_indexes = slice(None)
        self.channel_indexes = channel_indexes

        self.channels = self.neorawio.header['unit_channels'][channel_indexes]

        #TODO: something for multi segment
        self.block_index = 0
        self.seg_index = 0

    @property
    def nb_channel(self):
        return len(self.channels)

    def get_channel_name(self, chan=0):
        return self.channels[chan]['name']

    @property
    def t_start(self):
        t_start = self.neorawio.segment_t_start(self.block_index, self.seg_index)
        return t_start

    @property
    def t_stop(self):
        t_stop = self.neorawio.segment_t_stop(self.block_index, self.seg_index)
        return t_stop

    def get_chunk(self, chan=0,  i_start=None, i_stop=None):
        raise(NotImplementedError)

    def get_chunk_by_time(self, chan=0,  t_start=None, t_stop=None):
        spike_timestamp = self.neorawio.get_spike_timestamps(block_index=self.block_index,
                        seg_index=self.seg_index, unit_index=chan, t_start=t_start, t_stop=t_stop)

        spike_times = self.neorawio.rescale_spike_timestamp(spike_timestamp, dtype='float64')

        return spike_times

# this fit the new  neo rawio API >=0.10
class SpikeFromNeoRawIOSource(BaseSpikeSource):
    def __init__(self, neorawio, channel_indexes=None):
        self.neorawio =neorawio
        if channel_indexes is None:
            channel_indexes = slice(None)
        self.channel_indexes = channel_indexes

        self.channels = self.neorawio.header['spike_channels'][channel_indexes]

        #TODO: something for multi segment
        self.block_index = 0
        self.seg_index = 0

    @property
    def nb_channel(self):
        return len(self.channels)

    def get_channel_name(self, chan=0):
        return self.channels[chan]['name']

    @property
    def t_start(self):
        t_start = self.neorawio.segment_t_start(self.block_index, self.seg_index)
        return t_start

    @property
    def t_stop(self):
        t_stop = self.neorawio.segment_t_stop(self.block_index, self.seg_index)
        return t_stop

    def get_chunk(self, chan=0,  i_start=None, i_stop=None):
        raise(NotImplementedError)

    def get_chunk_by_time(self, chan=0,  t_start=None, t_stop=None):
        spike_timestamp = self.neorawio.get_spike_timestamps(block_index=self.block_index,
                        seg_index=self.seg_index, spike_channel_index=chan, t_start=t_start, t_stop=t_stop)

        spike_times = self.neorawio.rescale_spike_timestamp(spike_timestamp, dtype='float64')

        return spike_times



class EpochFromNeoRawIOSource(BaseEventAndEpoch):
    def __init__(self, neorawio, channel_indexes=None):
        self.neorawio =neorawio
        if channel_indexes is None:
            channel_indexes = slice(None)
        self.channel_indexes = channel_indexes

        self.channels = self.neorawio.header['event_channels'][channel_indexes]

        #TODO: something for multi segment
        self.block_index = 0
        self.seg_index = 0

        self._cache_event = {}

    @property
    def nb_channel(self):
        return len(self.channels)

    def get_channel_name(self, chan=0):
        return self.channels[chan]['name']

    @property
    def t_start(self):
        t_start = self.neorawio.segment_t_start(self.block_index, self.seg_index)
        return t_start

    @property
    def t_stop(self):
        t_stop = self.neorawio.segment_t_stop(self.block_index, self.seg_index)
        return t_stop

    def get_chunk(self, chan=0,  i_start=None, i_stop=None):
        k = (self.block_index , self.seg_index, chan)
        if k not in self._cache_event:
            self._cache_event[k] = self.get_chunk_by_time(chan=chan,  t_start=None, t_stop=None)

        ep_times, ep_durations, ep_labels = self._cache_event[k]

        ep_times = ep_times[i_start:i_stop]
        if ep_durations is not None:
            ep_durations = ep_durations[i_start:i_stop]
        ep_labels = ep_labels[i_start:i_stop]

        return ep_times, ep_durations, ep_labels

    def get_chunk_by_time(self, chan=0,  t_start=None, t_stop=None):

        ep_timestamps, ep_durations, ep_labels = self.neorawio.get_event_timestamps(block_index=self.block_index,
                        seg_index=self.seg_index, event_channel_index=chan, t_start=t_start, t_stop=t_stop)

        ep_times = self.neorawio.rescale_event_timestamp(ep_timestamps, dtype='float64')

        if ep_durations is not None:
            ep_durations = self.neorawio.rescale_epoch_duration(ep_durations, dtype='float64')
        else:
            ep_durations = np.zeros_like(ep_times)

        return ep_times, ep_durations, ep_labels





def get_sources_from_neo_rawio(neorawio):
    assert HAVE_NEO
    assert isinstance(neorawio, BaseRawIO)

    if neorawio.header is None:
        logger.info('parse header')
        neorawio.parse_header()

    sources = {'signal':[], 'epoch':[], 'spike':[]}

    
    # handle of neo version
    # this will be simplified in a while
    if hasattr(neorawio, 'get_group_signal_channel_indexes'):
        # Neo >= 0.9.0 and  < 0.10
        if neorawio.signal_channels_count() > 0:
            channel_indexes_list = neorawio.get_group_signal_channel_indexes()
            for channel_indexes in channel_indexes_list:
                #one soure by channel group
                sources['signal'].append(AnalogSignalFromNeoRawIOSource_until_v9(neorawio, channel_indexes))
    elif hasattr(neorawio, 'get_group_channel_indexes'):
        # Neo < 0.9.0
        if neorawio.signal_channels_count() > 0:
            channel_indexes_list = neorawio.get_group_signal_channel_indexes()
            for channel_indexes in channel_indexes_list:
                #one soure by channel group
                sources['signal'].append(AnalogSignalFromNeoRawIOSource_until_v9(neorawio, channel_indexes))
    elif hasattr(neorawio, 'signal_streams_count'):
        # Neo >= 0.10.0 (not release yet in march 2021)
        num_streams = neorawio.signal_streams_count()
        for stream_index in range(num_streams):
            #one soure by stream
            sources['signal'].append(AnalogSignalFromNeoRawIOSource(neorawio, stream_index))


    
    if hasattr(neorawio, 'unit_channels_count'):
        # Neo   < 0.10
        if neorawio.unit_channels_count()>0:
            sources['spike'].append(SpikeFromNeoRawIOSource_until_v9(neorawio, None))
    elif hasattr(neorawio, 'spike_channels_count'):
        # neo >= 0.10
        if neorawio.spike_channels_count()>0:
            sources['spike'].append(SpikeFromNeoRawIOSource(neorawio, None))
        

    if neorawio.event_channels_count()>0:
        sources['epoch'].append(EpochFromNeoRawIOSource(neorawio, None))



    return sources
