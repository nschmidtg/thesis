import torch
from unet_parts import down, up, input_layer, last_layer
from asteroid.models import BaseModel

class UNet(BaseModel):
    #def __init__(self, n_channels, n_classes, bilinear=True):
    def __init__(self, sample_rate, kernel_size, stride):
        super(UNet, self).__init__(sample_rate=sample_rate)
        self.kernel_size = kernel_size
        self.stride = stride

        # declare layers

        # input batch normalization
        self.input_layer_speech = input_layer(1)
        self.input_layer_music = input_layer(1)

        # down blocks for speech
        self.down_speech_1 = down(1, 16, self.kernel_size, self.stride)
        self.down_speech_2 = down(16, 32, self.kernel_size, self.stride)
        self.down_speech_3 = down(32, 64, self.kernel_size, self.stride)
        self.down_speech_4 = down(64, 128, self.kernel_size, self.stride)
        self.down_speech_5 = down(128, 256, self.kernel_size, self.stride)
        self.down_speech_6 = down(256, 512, self.kernel_size, self.stride)

        # down blocks for music
        self.down_music_1 = down(1, 16, self.kernel_size, self.stride)
        self.down_music_2 = down(16, 32, self.kernel_size, self.stride)
        self.down_music_3 = down(32, 64, self.kernel_size, self.stride)
        self.down_music_4 = down(64, 128, self.kernel_size, self.stride)
        self.down_music_5 = down(128, 256, self.kernel_size, self.stride)
        self.down_music_6 = down(256, 512, self.kernel_size, self.stride)

        # up blocks for speech
        self.up_speech_1 = up(512, 256, self.kernel_size, self.stride, (0,0), 1)
        self.up_speech_2 = up(256, 128, self.kernel_size, self.stride, (0,0), 2)
        self.up_speech_3 = up(128, 64, self.kernel_size, self.stride, (0,1), 3)
        self.up_speech_4 = up(64, 32, self.kernel_size, self.stride, (0,0), 4)
        self.up_speech_5 = up(32, 16, self.kernel_size, self.stride, (0,0), 5)

        # up blocks for music
        self.up_music_1 = up(512, 256, self.kernel_size, self.stride, (0,0), 1)
        self.up_music_2 = up(256, 128, self.kernel_size, self.stride, (0,0), 2)
        self.up_music_3 = up(128, 64, self.kernel_size, self.stride, (0,1), 3)
        self.up_music_4 = up(64, 32, self.kernel_size, self.stride, (0,0), 4)
        self.up_music_5 = up(32, 16, self.kernel_size, self.stride, (0,0), 5)

        # last layer sigmoid
        self.last_layer_speech = last_layer(16, 1, self.kernel_size, self.stride, (0, 0))
        self.last_layer_music = last_layer(16, 1, self.kernel_size, self.stride, (0, 0))



    def forward(self, X_in):
        # shape of X_in: [batch, mag/phase, bins, frames] must remove phase
        X_in = X_in.permute(1,0,2,3)[0]
        # add channels dimension
        X = X_in.unsqueeze(1)

        # input layer
        X_speech = self.input_layer_speech(X)
        X_music = self.input_layer_music(X)

        # first down layer
        X1_speech = self.down_speech_1(X_speech)
        X1_music = self.down_music_1(X_music)

        # second down layer
        X2_speech = self.down_speech_2(X1_speech)
        X2_music = self.down_music_2(X1_music)

        # third down layer
        X3_speech = self.down_speech_3(X2_speech)
        X3_music = self.down_music_3(X2_music)

        # # fourth down layer
        X4_speech = self.down_speech_4(X3_speech)
        X4_music = self.down_music_4(X3_music)

        # # 5 down layer
        X5_speech = self.down_speech_5(X4_speech)
        X5_music = self.down_music_5(X4_music)

        # # 6 down layer
        X6_speech = self.down_speech_6(X5_speech)
        X6_music = self.down_music_6(X5_music)


        # # first up layer
        # print("X5", X5_speech.shape, X6_speech.shape)
        X5_speech = self.up_speech_1(X5_speech, X6_speech)
        X5_music = self.up_music_1(X5_music, X6_music)

        # # 2 up layer
        X4_speech = self.up_speech_2(X4_speech, X5_speech)
        X4_music = self.up_music_2(X4_music, X5_music)

        # # 3 up layer
        X3_speech = self.up_speech_3(X3_speech, X4_speech)
        X3_music = self.up_music_3(X3_music, X4_music)

        # # 4 up layer
        X2_speech = self.up_speech_4(X2_speech, X3_speech)
        X2_music = self.up_music_4(X2_music, X3_music)

        # # 5 up layer
        X1_speech = self.up_speech_5(X1_speech, X2_speech)
        X1_music = self.up_music_5(X1_music, X2_music)

        # last up layer (no concat after transposed conv)
        X_speech = self.last_layer_speech(X1_speech)
        X_music = self.last_layer_music(X1_music)

        # remove channels dimension:
        X_speech = X_speech.squeeze(1)
        X_music = X_music.squeeze(1)

        # create the mask
        X_mask_speech = X_speech / (X_speech + X_music)
        # use mask to separate speech from mix
        speech = X_in * X_mask_speech
        # and music
        music = X_in * (1 - X_mask_speech)
        
        # add both sources to a tensor to return them
        T_data = torch.stack([speech, music], dim=1)

        return T_data

    def get_model_args(self):
        """Arguments needed to re-instantiate the model."""
        model_args = {
            "kernel_size": self.kernel_size,
            "stride": self.stride
        }
        return model_args