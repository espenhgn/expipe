import pyopenephys
import exdir
import shutil
import glob
import os
import quantities as pq
import numpy as np

from expipe.io.core import Filerecord
from expipe.io.core import user
from expipe import settings
import os.path as op

# TODO inform database about openephys data being included
# TODO avoid overwriting existing data!
# TODO SpikeTrain class - needs klusta stuff
# TODO filtering and downsampling


def _prepare_exdir_file(exdir_file):
    general = exdir_file.require_group("general")
    subject = general.require_group("subject")
    processing = exdir_file.require_group("processing")
    epochs = exdir_file.require_group("epochs")

    return general, subject, processing, epochs


def convert(openephys_directory, exdir_path):
    openephys_file = pyopenephys.File(openephys_directory)
    exdir_file = exdir.File(exdir_path)
    dtime = openephys_file._start_datetime.strftime('%Y-%m-%dT%H:%M:%S')
    exdir_file.attrs['session_start_time'] = dtime
    exdir_file.attrs['session_duration'] = openephys_file._duration
    acquisition = exdir_file.require_group("acquisition")
    general = exdir_file.require_group("general")
    processing = exdir_file.require_group("processing")
    subject = general.require_group("subject")

    target_folder = op.join(acquisition.directory, openephys_file.session)
    acquisition.attrs["openephys_session"] = openephys_file.session

    shutil.copytree(openephys_file._absolute_foldername, target_folder)

    print("Copied", openephys_file.session, "to", target_folder)


def load_openephys_file(exdir_file):
    acquisition = exdir_file["acquisition"]
    openephys_session = acquisition.attrs["openephys_session"]
    openephys_directory = op.join(acquisition.directory, openephys_session)
    return pyopenephys.File(openephys_directory)


def make_channel_groups(exdir_path):
    exdir_file = exdir.File(exdir_path)
    general, subject, processing, epochs = _prepare_exdir_file(exdir_file)
    openephys_file = load_openephys_file(exdir_file=exdir_file)
    channel_groups = {}
    elphys = processing.require_group('electrophysiology')
    for openephys_channel_group in openephys_file.channel_groups:
        exdir_channel_group = elphys.require_group(
            "channel_group_{}".format(openephys_channel_group.channel_group_id))

        channel_groups[openephys_channel_group.channel_group_id] = {
            'channel_group': exdir_channel_group,
            'openephys_file': openephys_file,
            'openephys_channel_group': openephys_channel_group,
            'start_time': 0 * pq.s,
            'stop_time': openephys_file._duration
        }

        channel_identities = np.array([ch.index for ch in openephys_channel_group.channels])
        exdir_channel_group.attrs['start_time'] = 0 * pq.s
        exdir_channel_group.attrs['stop_time'] = openephys_file._duration
        exdir_channel_group.attrs["electrode_identities"] = channel_identities
        exdir_channel_group.attrs["electrode_idx"] = channel_identities - channel_identities[0]
        exdir_channel_group.attrs['electrode_group_id'] = openephys_channel_group.channel_group_id
        # TODO else: test if attrs are the same
    return channel_groups


def generate_analog_signals(exdir_path):
    channel_groups = make_channel_groups(exdir_path)
    for channel_group_segment in channel_groups.values():
        channel_group = channel_group_segment['channel_group']
        openephys_file = channel_group_segment['openephys_file']
        openephys_channel_group = channel_group_segment['openephys_channel_group']
        start_time = channel_group_segment['start_time']
        stop_time = channel_group_segment['stop_time']
        lfp_index = 0
        for analog_signal in openephys_file.analog_signals:
            if openephys_channel_group == openephys_file.channel_group(analog_signal.channel_id):
                lfp_index += 1

                lfp = channel_group.require_group("LFP")

                lfp_timeseries = lfp.require_group("LFP_timeseries_{}".format(lfp_index))
                spike_train = openephys_channel_group.spike_train
                channel_identities = np.array([ch.index for ch in
                                               openephys_channel_group.channels])
                # TODO analog signals have only one channel
                lfp_timeseries.attrs["num_samples"] = len(analog_signal.signal)
                lfp_timeseries.attrs["start_time"] = start_time
                lfp_timeseries.attrs["stop_time"] = stop_time
                lfp_timeseries.attrs["sample_rate"] = analog_signal.sample_rate
                lfp_timeseries.attrs["electrode_identity"] = analog_signal.channel_id
                lfp_timeseries.attrs["electrode_idx"] = analog_signal.channel_id - openephys_channel_group.channel_group_id * 4
                lfp_timeseries.attrs['electrode_group_id'] = openephys_channel_group.channel_group_id
                data = lfp_timeseries.require_dataset("data", data=analog_signal.signal)
                data.attrs["num_samples"] = len(analog_signal.signal)
                # NOTE: In exdirio (python-neo) sample rate is required on dset #TODO
                data.attrs["sample_rate"] = analog_signal.sample_rate


def generate_clusters(exdir_path):
    channel_groups = make_channel_groups(exdir_path)
    for channel_group_segment in channel_groups.values():
        channel_group = channel_group_segment['channel_group']
        openephys_file = channel_group_segment['openephys_file']
        openephys_channel_group = channel_group_segment['openephys_channel_group']
        spike_train = openephys_channel_group.spike_train
        start_time = channel_group_segment['start_time']
        stop_time = channel_group_segment['stop_time']
        for cut in openephys_file.cuts:
            if(openephys_channel_group.channel_group_id == cut.channel_group_id):
                units = np.unique(cut.indices)
                cluster = channel_group.require_group("Clustering")
                cluster.attrs["start_time"] = start_time
                cluster.attrs["stop_time"] = stop_time
                # TODO: Add _ peak_over_rms as described in NWB
                cluster.attrs["peak_over_rms"] = None
                times = cluster.require_dataset("times", data=spike_train.times)
                times.attrs["num_samples"] = len(spike_train.times)
                clnums = cluster.require_dataset("cluster_nums", data=units)
                clnums.attrs["num_samples"] = len(units)
                nums = cluster.require_dataset("nums", data=cut.indices)
                nums.attrs["num_samples"] = len(cut.indices)


def generate_units(exdir_path):
    channel_groups = make_channel_groups(exdir_path)
    for channel_group_segment in channel_groups.values():
        channel_group = channel_group_segment['channel_group']
        openephys_file = channel_group_segment['openephys_file']
        openephys_channel_group = channel_group_segment['openephys_channel_group']
        spike_train = openephys_channel_group.spike_train
        start_time = channel_group_segment['start_time']
        stop_time = channel_group_segment['stop_time']

        for cut in openephys_file.cuts:
            if(openephys_channel_group.channel_group_id == cut.channel_group_id):
                unit_times = channel_group.require_group("UnitTimes")
                unit_times.attrs["start_time"] = start_time
                unit_times.attrs["stop_time"] = stop_time

                unit_ids = [i for i in np.unique(cut.indices) if i > 0]
                unit_ids = np.array(unit_ids) - 1  # -1 for pyhton convention
                for index in unit_ids:
                    unit = unit_times.require_group("unit_{}".format(index))
                    indices = np.where(cut.indices == index)[0]
                    times = spike_train.times[indices]
                    unit.require_dataset("times", data=times)
                    unit.attrs['num_samples'] = len(times)
                    unit.attrs["cluster_group"] = "Unsorted"
                    unit.attrs["cluster_id"] = int(index)
                    # TODO: Add unit_description (e.g. cell type) and source as in NWB
                    unit.attrs["source"] = None
                    unit.attrs["unit_description"] = None


def generate_spike_trains(exdir_path):
    channel_groups = make_channel_groups(exdir_path)
    for channel_group_segment in channel_groups.values():
        channel_group = channel_group_segment['channel_group']
        openephys_file = channel_group_segment['openephys_file']
        openephys_channel_group = channel_group_segment['openephys_channel_group']
        start_time = channel_group_segment['start_time']
        stop_time = channel_group_segment['stop_time']

        event_waveform = channel_group.require_group("EventWaveform")
        waveform_timeseries = event_waveform.require_group('waveform_timeseries')
        spike_train = openephys_channel_group.spike_train
        channel_identities = np.array([ch.index for ch in openephys_channel_group.channels])
        waveform_timeseries.attrs["num_samples"] = spike_train.spike_count
        waveform_timeseries.attrs["sample_length"] = spike_train.samples_per_spike
        waveform_timeseries.attrs["num_channels"] = len(channel_identities)
        waveform_timeseries.attrs["electrode_identities"] = channel_identities
        waveform_timeseries.attrs["electrode_idx"] = channel_identities - channel_identities[0]
        waveform_timeseries.attrs['electrode_group_id'] = openephys_channel_group.channel_group_id
        waveform_timeseries.attrs["start_time"] = start_time
        waveform_timeseries.attrs["stop_time"] = stop_time
        waveform_timeseries.attrs['sample_rate'] = spike_train.sample_rate
        if not isinstance(spike_train.waveforms, pq.Quantity):
            spike_train.waveforms = spike_train.waveforms * pq.uV # TODO fix pyxona
        data = waveform_timeseries.require_dataset("data", data=spike_train.waveforms)
        data.attrs["num_samples"] = spike_train.spike_count
        data.attrs["sample_length"] = spike_train.samples_per_spike
        data.attrs["num_channels"] = len(channel_identities)
        data.attrs['sample_rate'] = spike_train.sample_rate
        times = waveform_timeseries.require_dataset("timestamps",
                                                    data=spike_train.times)
        times.attrs["num_samples"] = spike_train.spike_count


def generate_tracking(exdir_path):
    exdir_file = exdir.File(exdir_path)
    general, subject, processing, epochs = _prepare_exdir_file(exdir_file)
    openephys_file = load_openephys_file(exdir_file=exdir_file)
    tracking = processing.require_group('tracking')
    # NOTE openephys supports only one camera, but other setups might support several
    camera = tracking.require_group("camera_0")
    position = camera.require_group("Position")
    position.attrs['start_time'] = 0 * pq.s
    position.attrs['stop_time'] = openephys_file._duration
    tracking_data = openephys_file.tracking
    times, coords = tracking_data.times, tracking_data.positions
    tracked_spots = int(coords.shape[1] / 2)  # 2 coordinates per spot
    for n in range(tracked_spots):
        led = position.require_group("led_" + str(n))
        data = coords[:, n * 2: n * 2 + 1 + 1]
        dset = led.require_dataset('data', data)
        dset.attrs['num_samples'] = len(data)
        dset = led.require_dataset("timestamps", times)
        dset.attrs['num_samples'] = len(times)
        led.attrs['start_time'] = 0 * pq.s
        led.attrs['stop_time'] = openephys_file._duration


def generate_inp(exdir_path):
    # TODO should we save duration as attr or use start-stop time?
    exdir_file = exdir.File(exdir_path)
    general, subject, processing, epochs = _prepare_exdir_file(exdir_file)
    openephys_file = load_openephys_file(exdir_file=exdir_file)
    inp = epochs.require_group("openephys_inp")

    if not all(key in inp.attrs for key in ['start_time', 'stop_time']):
        inp.attrs['start_time'] = 0 * pq.s
        inp.attrs['stop_time'] = openephys_file._duration

    inp_data = openephys_file.inp_data
    times = inp.require_dataset('timestamps', inp_data.times)
    times.attrs['num_samples'] = len(times[:])
    types = inp.require_dataset('event_types', inp_data.event_types)
    types.attrs['num_samples'] = len(types[:])
    vals = inp.require_dataset('values', inp_data.values)
    vals.attrs['num_samples'] = len(vals[:])


class OpenEphysFilerecord(Filerecord):
    def __init__(self, action, filerecord_id=None):
        super().__init__(action, filerecord_id)

    def import_file(self, openephys_directory):
        convert(openephys_directory=openephys_directory,
                exdir_path=op.join(settings["data_path"], self.local_path))

    def generate_tracking(self):
        generate_tracking(self.local_path)

    def generate_analog_signals(self):
        generate_analog_signals(self.local_path)

    def generate_spike_trains(self):
        generate_spike_trains(self.local_path)

    def generate_inp(self):
        generate_inp(self.local_path)

    def generate_units(self):
        generate_units(self.local_path)

    def generate_clusters(self):
        generate_clusters(self.local_path)

if __name__ == '__main__':
    openephys_directory = '/home/mikkel/apps/expipe-project/openephystest/1753_2017-03-07_18-40-14_ephys-trackred'
    exdir_path = '/home/mikkel/apps/expipe-project/openephystest.exdir'
    # convert(openephys_directory=openephys_directory,
    #         exdir_path=exdir_path)
    generate_tracking(exdir_path)
    generate_analog_signals(exdir_path)
    generate_spike_trains(exdir_path)
    generate_inp(exdir_path)
    generate_units(exdir_path)
    generate_clusters(exdir_path)