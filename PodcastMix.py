import torch
from torch.utils.data import Dataset
import pandas as pd
import torchaudio
import os
import numpy as np
import random
from math import sqrt

class PodcastMix(Dataset):
    """Dataset class for PodcastMix source separation tasks.
    This dataset created Podcasts-like mixes on the fly consisting in
    2 sources: background music and foreground speech
    Args:
        csv_dir (str): The path to the metadata files: speech.csv and music.csv
        sample_rate (int) : The sample rate of the sources and mixtures.
        segment (int) : The desired sources and mixtures length in s.
    References
        [1] "Jamendo....
        [2] "VCTK...
    """

    dataset_name = "PodcastMix"

    def __init__(self, csv_dir, sample_rate=44100, segment=2,
                 shuffle_tracks=False, multi_speakers=False, solo_music_ratio=0.2):
        self.csv_dir = csv_dir
        self.speech_csv_path = os.path.join(self.csv_dir, 'speech.csv')
        self.music_csv_path = os.path.join(self.csv_dir, 'music.csv')
        self.segment = segment
        self.segment_total = 12
        self.sample_rate = sample_rate
        self.shuffle_tracks = shuffle_tracks
        self.multi_speakers = multi_speakers
        self.solo_music_ratio = solo_music_ratio
        # Open csv files
        self.df_speech = pd.read_csv(self.speech_csv_path, engine='python')
        self.df_music = pd.read_csv(self.music_csv_path, engine='python')
        # create dictionary of speakers
        # df_speech.loc[df_speech['speaker_id'] == "p257"]
        # initialize indexes
        self.speech_inxs = list(range(len(self.df_speech)))
        self.music_inxs = list(range(len(self.df_music)))
        self.gain_ramp = np.array(range(1, 100, 1))/100
        np.random.shuffle(self.gain_ramp)
        torchaudio.set_audio_backend(backend='soundfile')

    def __len__(self):
        # for now, its a full permutation
        return min([len(self.df_speech), len(self.df_music)])


    def compute_rand_offset_duration(self, original_sr, original_num_frames):
        """ Computes a random offset and the number of frames to read the audio_path
        in order to get a subsection of length equal to self.segment. If the number 
        of frames in the segment is bigger than the original_num_frames, it returns
        0 for the offset and the number of frames contained in the audio.

        Parameters:
        - audio_path (str) : path to the audio file
        - original_sr (int) : sample rate of the audio file
        - original_num_frames (int) : number of frames of the full audio file

        Returns (tuple):
        - offset (int) : the computed random offset in frames where the audio should be 
        loaded
        - segment_frames (int) : the number of frames contained in the segment. If number
        of frames contained in the audio is smaller than the number of frames contained
        in the segment at the self.sample_rate sample rate, the offset is 0 and the 
        segment_frames will be equal to the length of the file
        """
        offset = 0
        segment_frames = int(self.segment_total * original_sr)
        if segment_frames > original_num_frames:
            segment_frames = original_num_frames
        else:
            offset = int(random.uniform(0, original_num_frames - segment_frames))

        return offset, segment_frames

    def load_mono_non_silent_random_segment(self, audio_path):
        """ Randomly selects a non_silent part of the audio given by audio_path

        Parameters:
        - audio_path (str) : path to the audio file

        Returns:
        - audio_signal (torchaudio) : waveform of the
        """
        info = torchaudio.info(audio_path)
        sr, length = info.sample_rate, info.num_frames
        audio_signal = torch.tensor([0.])
        # iterate until the segment is not silence
        while torch.sum(torch.abs(audio_signal)) == 0:
            # If there is a seg, start point is set randomly
            offset, duration = self.compute_rand_offset_duration(
                sr,
                length
            )
            # load the audio with the computed offsets
            audio_signal, sr = torchaudio.load(
                audio_path,
                frame_offset=offset,
                num_frames=duration,
                normalize=True
            )
        # convert to mono
        if len(audio_signal) == 2:
            audio_signal = torch.mean(audio_signal, dim=0).unsqueeze(0)
        # resample if sr is different than the specified in dataloader
        if not sr == self.sample_rate:
            audio_signal = torchaudio.transforms.Resample(orig_freq = sr, new_freq = self.sample_rate)(audio_signal)
        # zero pad if the size is smaller than seq_duration
        seq_duration_samples = int(self.segment * self.sample_rate)
        total_samples = audio_signal.shape[-1]
        if seq_duration_samples > total_samples:
            padding_offset = random.randint(0, seq_duration_samples - total_samples)
            audio_signal = torch.nn.ConstantPad1d(
                (
                    padding_offset,
                    seq_duration_samples - total_samples - padding_offset
                ),
                0
            )(audio_signal)

        return audio_signal

    def rms(self, speech, music):
        """ computes the RMS of an audio signal
        """
        
        speech = speech[speech.nonzero()]
        
        return torch.sqrt(torch.mean(speech ** 2)) / torch.sqrt(torch.mean(music ** 2))

    def load_speechs(self, speech_idx):
        """ Loads the speaker mix. It could be a single speaker if
        self.multi_speaker=False, or a random mix of 1 to 4
        phrases from the speaker of speech_idx.
        """
        speaker_csv_id = self.df_speech.iloc[speech_idx].speaker_id
        # filter the speechs by speaker id
        speaker_dict = self.df_speech.loc[
            self.df_speech['speaker_id'] == speaker_csv_id
        ]
        speech_mix = torch.zeros(self.segment_total * self.sample_rate)
        speech_acum = 0
        speechs = []
        num_of_zeros = len(speech_mix) * self.solo_music_ratio
        while(speech_acum < (len(speech_mix) - num_of_zeros)):
            row_speech = speaker_dict.sample()
            audio_length = int(row_speech['length'])
            
            audio_path = row_speech['speech_path'].values[0]
            
            
            if audio_length > (len(speech_mix) - speech_acum - num_of_zeros):
                duration = len(speech_mix) - speech_acum - num_of_zeros
            else:
                duration = audio_length
            audio_signal, _ = torchaudio.load(
                audio_path,
                frame_offset=0,
                num_frames=int(duration),
                normalize=True
            )
            
            speechs.append(audio_signal.squeeze(0))
            
            speech_acum += duration
        
        silence_segments = len(speechs) + 1
        
        mean = (len(speech_mix) - speech_acum) // silence_segments
        print("mean", mean, silence_segments)
        silence_segment_lengths = np.random.normal(mean, sqrt(mean), silence_segments)
        print("0", silence_segment_lengths)
        # make sure there are no negative values
        silence_segment_lengths[silence_segment_lengths < 0] = 0
        print("1", silence_segment_lengths)
        silences_norm = silence_segment_lengths / np.sum(silence_segment_lengths)
        print("2", silences_norm)
        silence_segment_lengths = silences_norm * (len(speech_mix) - speech_acum)
        print("3", silence_segment_lengths)
        i = 0
        index = 0
        print("largo de speech_mix", len(speech_mix))
        for speech in speechs:
            print("len de silencio", int(silence_segment_lengths[index]))
            print("len de speech", len(speech))
            i += int(silence_segment_lengths[index])
            speech_mix[i:i + len(speech)] = speech
            i += len(speech)
            print("remaining", len(speech_mix) - i)
         
            #i += len(speech)
            
            # i += int(silence_segment_lengths[index])
            index += 1
            
        return speech_mix


    def __getitem__(self, idx):
        if(idx == 0 and self.shuffle_tracks):
            # shuffle on first epochs of training and validation. Not testing
            random.shuffle(self.music_inxs)
            random.shuffle(self.speech_inxs)
        # get random offset
        offset_truncate = int(random.uniform(0, self.segment_total * self.sample_rate - self.segment * self.sample_rate))
        # get corresponding index from the list
        music_idx = self.music_inxs[idx]
        speech_idx = self.speech_inxs[idx]
        # Get the row in speech dataframe
        row_music = self.df_music.iloc[music_idx]
        sources_list = []

        speech_signal = self.load_speechs(speech_idx)
        
        speech_signal = speech_signal[offset_truncate:offset_truncate + self.segment * self.sample_rate]
        
        sources_list.append(speech_signal)

        # now for music:
        music_signal = self.load_mono_non_silent_random_segment(row_music['music_path'])
        music_signal = music_signal.squeeze(0)
        music_signal = music_signal[offset_truncate:offset_truncate + (self.segment * self.sample_rate)]
        
        # music_signal = music_signal.squeeze(0)
        
        # gain based on RMS in order to have RMS(speech_signal) >= RMS(music_singal)
        reduction_factor = self.rms(speech_signal, music_signal)

        # now we know that rms(r * music_signal) == rms(speech_signal)
        if self.shuffle_tracks:
            # random gain for training and validation
            music_gain = random.uniform(1e-2, 1) * reduction_factor
        else:
            # fixed gain for testing
            music_gain = self.gain_ramp[idx % len(self.gain_ramp)] * reduction_factor

        # multiply the music by the gain factor and add to the sources_list
        
        music_signal = music_gain * music_signal
        
        
        # music_signal = music_signal[offset_truncate:offset_truncate + (self.segment * self.sample_rate)]
        
        sources_list.append(music_signal)

        
        # compute the mixture
        mixture = sources_list[0] + sources_list[1]
        mixture = torch.squeeze(mixture)

        # Stack sources
        sources = np.vstack(sources_list)
        # Convert sources to tensor
        sources = torch.from_numpy(sources)

        return mixture, sources

    def get_infos(self):
        """Get dataset infos (for publishing models).
        Returns:
            dict, dataset infos with keys `dataset`, `task` and `licences`.
        """
        infos = dict()
        infos["dataset"] = self.dataset_name
        return infos
