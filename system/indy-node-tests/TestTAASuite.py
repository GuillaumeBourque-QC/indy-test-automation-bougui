import pytest
from system.utils import *
SEC_PER_DAY = 24 * 60 * 60


@pytest.mark.usefixtures('docker_setup_and_teardown')
class TestTAASuite:

    @pytest.mark.parametrize(
        'aml, version_set, context, version_get',
        [
            ({random_string(10): random_string(10)}, '0', random_string(25), '0'),
            ({random_string(100): random_string(100)}, random_string(5), None, None)
        ]
    )
    @pytest.mark.asyncio
    async def test_case_send_and_get_aml(
            self, pool_handler, wallet_handler, get_default_trustee, aml, version_set, context, version_get
    ):
        trustee_did, _ = get_default_trustee
        req = ledger.build_acceptance_mechanisms_request(trustee_did, json.dumps(aml), version_set, context)
        res1 = await sign_and_submit_request(pool_handler, wallet_handler, trustee_did, req)
        # assert res1['op'] == 'REPLY'
        assert res1['txnMetadata']['seqNo'] is not None
        # aml with the same version should be rejected
        req = ledger.build_acceptance_mechanisms_request(trustee_did, json.dumps(aml), version_set, context)
        with pytest.raises(indy_vdr.error.VdrError):
            res2 = await sign_and_submit_request(pool_handler, wallet_handler, trustee_did, req)
        # assert res2['op'] == 'REJECT'
        timestamp = int(time.time()) if version_get is None else None
        req = ledger.build_get_acceptance_mechanisms_request(None, timestamp, version_get)
        res3 = await pool_handler.submit_request(req)
        # assert res3['op'] == 'REPLY'
        assert res3['seqNo'] is not None

    @pytest.mark.skip('INDY-2316')
    @pytest.mark.parametrize(
        'taa_text, taa_ver',
        [
            (random_string(1), random_string(100)),
            (random_string(100), random_string(1))
        ]
    )
    @pytest.mark.asyncio
    async def test_case_send_and_get_taa(self, pool_handler, wallet_handler, get_default_trustee, taa_text, taa_ver):
        trustee_did, _ = get_default_trustee
        # no aml in ledger - should be rejected
        req = await ledger.build_txn_author_agreement_request(trustee_did, taa_text, taa_ver)
        res1 = json.loads(await ledger.sign_and_submit_request(pool_handler, wallet_handler, trustee_did, req))
        assert res1['op'] == 'REJECT'
        aml_key = 'aml_key'
        # add AML
        req = await ledger.build_acceptance_mechanisms_request(
            trustee_did, json.dumps({aml_key: random_string(5)}), random_string(10), None
        )
        res2 = json.loads(await ledger.sign_and_submit_request(pool_handler, wallet_handler, trustee_did, req))
        assert res2['op'] == 'REPLY'
        # add non-latest TAA
        req = await ledger.build_txn_author_agreement_request(trustee_did, 'non-latest-text', 'non-latest-version')
        res = json.loads(await ledger.sign_and_submit_request(pool_handler, wallet_handler, trustee_did, req))
        assert res['op'] == 'REPLY'
        # add non-latest TAA with the same version and text - should be rejected
        req = await ledger.build_txn_author_agreement_request(trustee_did, 'non-latest-text', 'non-latest-version')
        res = json.loads(await ledger.sign_and_submit_request(pool_handler, wallet_handler, trustee_did, req))
        assert res['op'] == 'REJECT'
        # add non-latest TAA with the same version but different text - should be rejected
        req = await ledger.build_txn_author_agreement_request(trustee_did, 'some-other-text', 'non-latest-version')
        res = json.loads(await ledger.sign_and_submit_request(pool_handler, wallet_handler, trustee_did, req))
        assert res['op'] == 'REJECT'
        # add the latest TAA
        req = await ledger.build_txn_author_agreement_request(trustee_did, taa_text, taa_ver)
        res3 = json.loads(await ledger.sign_and_submit_request(pool_handler, wallet_handler, trustee_did, req))
        assert res3['op'] == 'REPLY'
        # no taa in nym request
        res4 = await send_nym(pool_handler, wallet_handler, trustee_did, random_did_and_json()[0])
        assert res4['op'] == 'REJECT'
        # no taa in schema request
        _, res5 = await send_schema(
            pool_handler, wallet_handler, trustee_did, random_string(5), '1.0', json.dumps([random_string(10)])
        )
        assert res5['op'] == 'REJECT'
        # add non-latest taa to nym
        req66 = await ledger.build_nym_request(trustee_did, random_did_and_json()[0], None, None, None)
        req66 = await ledger.append_txn_author_agreement_acceptance_to_request(
            req66, 'non-latest-text', 'non-latest-version', None, aml_key, int(time.time())
        )
        res66 = json.loads(await ledger.sign_and_submit_request(pool_handler, wallet_handler, trustee_did, req66))
        assert res66['op'] == 'REJECT'
        # add taa to nym
        req6 = await ledger.build_nym_request(trustee_did, random_did_and_json()[0], None, None, None)
        req6 = await ledger.append_txn_author_agreement_acceptance_to_request(
            req6, taa_text, taa_ver, None, aml_key, int(time.time())
        )
        res6 = json.loads(await ledger.sign_and_submit_request(pool_handler, wallet_handler, trustee_did, req6))
        assert res6['op'] == 'REPLY'
        # add non-latest taa to schema
        schema_id, schema_json = await anoncreds.issuer_create_schema(
            trustee_did, random_string(5), '1.0', json.dumps([random_string(10)])
        )
        req77 = await ledger.build_schema_request(trustee_did, schema_json)
        req77 = await ledger.append_txn_author_agreement_acceptance_to_request(
            req77, 'non-latest-text', 'non-latest-version', None, aml_key, int(time.time())
        )
        res77 = json.loads(await ledger.sign_and_submit_request(pool_handler, wallet_handler, trustee_did, req77))
        assert res77['op'] == 'REJECT'
        # add taa to schema
        schema_id, schema_json = await anoncreds.issuer_create_schema(
            trustee_did, random_string(5), '1.0', json.dumps([random_string(10)])
        )
        req7 = await ledger.build_schema_request(trustee_did, schema_json)
        req7 = await ledger.append_txn_author_agreement_acceptance_to_request(
            req7, taa_text, taa_ver, None, aml_key, int(time.time())
        )
        res7 = json.loads(await ledger.sign_and_submit_request(pool_handler, wallet_handler, trustee_did, req7))
        assert res7['op'] == 'REPLY'
        # special positive case
        req8 = await ledger.build_nym_request(trustee_did, random_did_and_json()[0], None, None, None)
        req8 = await ledger.append_txn_author_agreement_acceptance_to_request(
            req8, taa_text, taa_ver, None, aml_key, int(time.time())
        )
        await asyncio.sleep(181)
        res8 = json.loads(await ledger.sign_and_submit_request(pool_handler, wallet_handler, trustee_did, req8))
        assert res8['op'] == 'REPLY'
        # get the latest TAA
        req9 = await ledger.build_get_txn_author_agreement_request(None, None)
        res9 = json.loads(await ledger.submit_request(pool_handler, req9))
        assert res9['op'] == 'REPLY'
        assert res9['result']['seqNo'] is not None
        # get non-latest TAA by version
        req10 = await ledger.build_get_txn_author_agreement_request(None, json.dumps({'version': 'non-latest-version'}))
        res10 = json.loads(await ledger.submit_request(pool_handler, req10))
        assert res10['op'] == 'REPLY'
        assert res10['result']['seqNo'] is not None
        # get nonexistent TAA
        req11 = await ledger.build_get_txn_author_agreement_request(None, json.dumps({'version': 'some version'}))
        res11 = json.loads(await ledger.submit_request(pool_handler, req11))
        assert res11['op'] == 'REPLY'
        assert res11['result']['seqNo'] is None

    @pytest.mark.skip('INDY-2316')
    @pytest.mark.asyncio
    async def test_aml_taa_negative_cases(self, pool_handler, wallet_handler, get_default_trustee):
        aml = {}
        aml_key = aml_ver = taa_ver = random_string(5)
        aml_val = taa_text = random_string(25)
        trustee_did, _ = get_default_trustee
        req =\
            {
                'protocolVersion': 2,
                'reqId': 1,
                'identifier': trustee_did,
                'operation':
                    {
                        'type': '5',
                        'aml': aml,
                        'version': '1'
                    }
            }
        res1 = json.loads(
            await ledger.sign_and_submit_request(pool_handler, wallet_handler, trustee_did, json.dumps(req))
        )
        assert res1['op'] == 'REQNACK'
        req = await ledger.build_txn_author_agreement_request(trustee_did, 'text', '1')
        res2 = json.loads(
            await ledger.sign_and_submit_request(pool_handler, wallet_handler, trustee_did, req)
        )
        assert res2['op'] == 'REJECT'
        req = await ledger.build_acceptance_mechanisms_request(
            trustee_did, json.dumps({aml_key: aml_val}), aml_ver, None
        )
        res3 = json.loads(await ledger.sign_and_submit_request(pool_handler, wallet_handler, trustee_did, req))
        assert res3['op'] == 'REPLY'
        req = await ledger.build_txn_author_agreement_request(trustee_did, taa_text, taa_ver)
        res4 = json.loads(await ledger.sign_and_submit_request(pool_handler, wallet_handler, trustee_did, req))
        assert res4['op'] == 'REPLY'
        # send txn with taa with precise timestamp - it doesn't work with libindy fixes so fix time manually
        req = await ledger.build_nym_request(trustee_did, random_did_and_json()[0], None, None, None)
        req = await ledger.append_txn_author_agreement_acceptance_to_request(
            req, taa_text, taa_ver, None, aml_key, int(time.time())
        )
        req = json.loads(req)
        req['taaAcceptance']['time'] += 999
        res6 = json.loads(
            await ledger.sign_and_submit_request(pool_handler, wallet_handler, trustee_did, json.dumps(req))
        )
        print(res6)
        assert res6['op'] == 'REJECT'
        # send txn with taa with timestamp from yesterday
        req = await ledger.build_nym_request(trustee_did, random_did_and_json()[0], None, None, None)
        req = await ledger.append_txn_author_agreement_acceptance_to_request(
            req, taa_text, taa_ver, None, aml_key, int(time.time()) // SEC_PER_DAY * SEC_PER_DAY - SEC_PER_DAY
        )
        res7 = json.loads(await ledger.sign_and_submit_request(pool_handler, wallet_handler, trustee_did, req))
        assert res7['op'] == 'REJECT'
        # send txn with taa with timestamp from tomorrow
        req = await ledger.build_nym_request(trustee_did, random_did_and_json()[0], None, None, None)
        req = await ledger.append_txn_author_agreement_acceptance_to_request(
            req, taa_text, taa_ver, None, aml_key, int(time.time()) // SEC_PER_DAY * SEC_PER_DAY + SEC_PER_DAY
        )
        res8 = json.loads(await ledger.sign_and_submit_request(pool_handler, wallet_handler, trustee_did, req))
        assert res8['op'] == 'REJECT'
