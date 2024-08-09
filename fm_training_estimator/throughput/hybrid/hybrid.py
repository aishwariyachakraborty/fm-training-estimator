# Standard
import logging

# Local
from ...config import FMArguments, HFTrainingArguments, InfraArguments
from ...regressor import LookupRegressor, XGBoostRegressor
from ...utils import extract_model_features


class HybridSpeedEstimator:
    def __init__(
        self,
        fm_args: FMArguments,
        train_args: HFTrainingArguments,
        infra_args: InfraArguments,
        lookup_data_path,
        model_path,
        use_model_features=False,
    ):

        self.fm = fm_args
        self.ta = train_args
        self.ia = infra_args
        self.lookup_est = None
        self.reg_est = None

        self.use_model_features = use_model_features

        # Lookup based estimator
        if lookup_data_path is not None:
            self.lookup_est = LookupRegressor(lookup_data_path)

        # Model based estimator
        if model_path is not None:
            self.reg_est = XGBoostRegressor(model_path)

        if lookup_data_path is None and model_path is None:
            logging.error(
                "This Estimator cannot function without any regressor module. Please init at least one of 2 regression modules to continue."
            )
            raise RuntimeError("HybridSpeedEstimator not properly initialized")

    def check_lookup(self, seqlen):
        lookup_query = {
            "model_name": self.fm.base_model_path,
            "number_gpus": self.ia.numGpusPerPod,
            "batch_size": self.ta.per_device_train_batch_size,
            "seq_len": seqlen,
        }

        if self.use_model_features:
            model_name = lookup_query.pop("model_name")
            lookup_query = lookup_query | extract_model_features(model_name)

        res = self.lookup_est.run(lookup_query)

        if res.empty:
            return None

        logging.info(res)
        return res[0:1]["tokens_per_second"].item()

    def get_tps(self, seqlen=None):
        if seqlen is None:
            seqlen = self.fm.block_size

        res = None

        # attempt lookup
        if self.lookup_est is not None:
            res = self.check_lookup(seqlen)
            if res is not None:
                return res

        if self.reg_est is None:
            return res

        # attempt reg approach
        params = [
            self.fm.base_model_path,
            self.ia.numGpusPerPod,
            self.ta.per_device_train_batch_size,
            int(seqlen),
        ]

        if self.use_model_features:
            model_name = params[0]
            params = extract_model_features(model_name, fmt="list") + params[1:]

        res = self.reg_est.run(params)

        # tps is 1st entry in the list
        return res[0][0]
