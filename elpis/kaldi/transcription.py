from pathlib import Path
from .resample import resample
from .command import run
from .fsobject import FSObject
from io import BufferedIOBase
import shutil
import subprocess


class Transcription(FSObject):
    _config_file = "transcription.json"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.audio_file_path = self.path.joinpath('audio.wav')
        self.model = None

    def link(self, model):
        self.model = model

    def _cook_generate_infer_files(self):
        # cook the infer file generator
        # TODO fix below
        with open('/kaldi-helpers/kaldi_helpers/inference_scripts/generate-infer-files.sh', 'r') as fin:
            generator: str = fin.read()
        generator = generator.replace('working_dir/input/infer', f'{self.path}')
        generator = generator.replace('working_dir/input/output/kaldi/data/test',
                                      f"{self.model.path.joinpath('kaldi', 'data', 'test')}")
        generator = generator.replace('working_dir/input/output/kaldi/data/infer',
                                      f"{self.model.path.joinpath('kaldi', 'data', 'infer')}")
        generator_file_path = self.path.joinpath('gen-infer-files.sh')
        with generator_file_path.open(mode='w') as fout:
            fout.write(generator)
        run(f'chmod +x {generator_file_path}')
        run(f'{generator_file_path}')

    def _process_audio_file(self, audio):
        # copy audio to the tmp folder for resampling
        tmp_path = Path(f'/tmp/{self.hash}')
        tmp_path.mkdir(parents=True, exist_ok=True)
        tmp_file_path = tmp_path.joinpath('original.wav')
        if isinstance(audio, Path) or isinstance(audio, str):
            shutil.copy(f'{audio}', f'{tmp_file_path}')
        elif isinstance(audio, BufferedIOBase):
            with tmp_file_path.open(mode='wb') as fout:
                fout.write(audio.read())
        # resample the audio fie
        resample(tmp_file_path, self.path.joinpath('audio.wav'))

    def _bake_gmm_decode_align(self):
        with open('/kaldi-helpers/kaldi_helpers/inference_scripts/gmm-decode-align.sh', 'r') as fin:
            content: str = fin.read()
        content = content.replace('../../../../kaldi_helpers/output_scripts/ctm_to_textgrid.py',
                                  '/kaldi-helpers/kaldi_helpers/output_scripts/ctm_to_textgrid.py')
        content = content.replace('../../../../kaldi_helpers/output_scripts/textgrid_to_elan.py',
                                  '/kaldi-helpers/kaldi_helpers/output_scripts/textgrid_to_elan.py')
        decode_file_path = self.path.joinpath('gmm-decode-align.sh')
        with decode_file_path.open(mode='w') as fout:
            fout.write(content)
        run(f'chmod +x {decode_file_path}')
        p = subprocess.run(f'sh {decode_file_path}'.split(), cwd=f'{self.model.path.joinpath("kaldi")}', check=True)

    def transcribe(self, audio):
        self._process_audio_file(audio)
        self._cook_generate_infer_files()

        kaldi_infer_path = self.model.path.joinpath('kaldi', 'data', 'infer')
        kaldi_test_path = self.model.path.joinpath('kaldi', 'data', 'test')
        kaldi_path = self.model.path.joinpath('kaldi')

        # run gmm-decoder
        shutil.copytree(f'{self.path}', f"{kaldi_infer_path}")
        shutil.copy(f'{self.audio_file_path}', f"{self.model.path.joinpath('kaldi', 'audio.wav')}")
        subprocess.run('sh /kaldi-helpers/kaldi_helpers/inference_scripts/gmm-decode.sh'.split(),
                       cwd=f'{self.model.path.joinpath("kaldi")}', check=True)

        # move results
        cmd = f"cp {kaldi_infer_path}/one-best-hypothesis.txt {self.path}/ && "
        cmd += f"infer_audio_filename=$(head -n 1 {kaldi_test_path}/wav.scp | awk '{{print $2}}' |  cut -c 3- ) && "
        cmd += f"cp \"{kaldi_path}/$infer_audio_filename\" {self.path}"
        run(cmd)

    def transcribe_align(self, audio):
        self._process_audio_file(audio)
        self._cook_generate_infer_files()

        kaldi_infer_path = self.model.path.joinpath('kaldi', 'data', 'infer')

        # run gmm-decoder-align
        shutil.copytree(f'{self.path}', f"{kaldi_infer_path}")
        shutil.copy(f'{self.audio_file_path}', f"{self.model.path.joinpath('kaldi', 'audio.wav')}")
        self._bake_gmm_decode_align()
        # p = subprocess.run('sh /kaldi-helpers/kaldi_helpers/inference_scripts/gmm-decode-align.sh'.split(),
        # cwd=f'{self.model.path.joinpath("kaldi")}')

        # move results
        # cmd = f"cp {kaldi_infer_path}/one-best-hypothesis.txt {self.path}/ && "
        # cmd += f"infer_audio_filename=$(head -n 1 {kaldi_test_path}/wav.scp | awk '{{print $2}}' |  cut -c 3- ) && "
        # cmd += f"cp \"{kaldi_path}/$infer_audio_filename\" {self.path}"
        # run(cmd)
        shutil.copy(f"{kaldi_infer_path.joinpath('utterance-0.eaf')}", f'{self.path}/{self.hash}.eaf')

    def elan(self):
        with open(f'{self.path}/{self.hash}.eaf', 'rb') as fin:
            return fin.read()
