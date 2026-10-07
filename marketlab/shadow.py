"""Version-frozen local shadow experiment definitions."""
import hashlib
from .data import json_text, now

DEFINITION = dict(version='official-shadow-v1',policy_version='trade-policy-v1',kind='stock',
    top=10,weights=dict(baseline=.7,institution=.2,revenue=.1),window=5,revenue_max_months=3,
    warmup=30,purge=10,test=10,block=10,minimum_test_days=30,bootstrap=2000,seed=20261008,
    selection='same eligible original candidate cohort; deterministic percentile ranks',
    fitting='none; weights fixed before collection; test dates never used for selection')
DEFINITION_HASH=hashlib.sha256(json_text(DEFINITION).encode()).hexdigest()


def freeze_definition(store):
    key='shadow_definition:'+DEFINITION['version']
    existing=store.get(key)
    if existing and existing['sha256']!=DEFINITION_HASH: raise ValueError('實驗定義改變，請建立新版本')
    if not existing:
        store.put(key,dict(definition=DEFINITION,sha256=DEFINITION_HASH,frozen_at=now().isoformat()))
