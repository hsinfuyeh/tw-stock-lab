"""Strict, pure parsers for official context. Never infer missing values as zero."""
from datetime import date, datetime
import math
import re
from .data import TAIPEI

VERSION = 'official-parser-v1'
SOURCES = ('institution', 'margin', 'revenue', 'announcement', 'action')
T86_FIELDS = ['證券代號','證券名稱','外陸資買進股數(不含外資自營商)',
    '外陸資賣出股數(不含外資自營商)','外陸資買賣超股數(不含外資自營商)',
    '外資自營商買進股數','外資自營商賣出股數','外資自營商買賣超股數',
    '投信買進股數','投信賣出股數','投信買賣超股數','自營商買賣超股數',
    '自營商買進股數(自行買賣)','自營商賣出股數(自行買賣)','自營商買賣超股數(自行買賣)',
    '自營商買進股數(避險)','自營商賣出股數(避險)','自營商買賣超股數(避險)','三大法人買賣超股數']
MARGIN_FIELDS = ['代號','名稱','買進','賣出','現金償還','前日餘額','今日餘額','次一營業日限額',
    '買進','賣出','現券償還','前日餘額','今日餘額','次一營業日限額','資券互抵','註記']


def official_date(value):
    text = re.sub(r'[/\-]', '', str(value).strip())
    if not text.isdigit() or len(text) not in (7, 8): raise ValueError('官方日期格式不符')
    year = int(text[:-4]) + (1911 if len(text) == 7 else 0)
    return date(year, int(text[-4:-2]), int(text[-2:])).isoformat()


def numeric(value, optional=False):
    try:
        result = float(str(value).strip().replace(',', ''))
        if not math.isfinite(result): raise ValueError('非有限數字')
        return int(result) if result.is_integer() else result
    except (ValueError, TypeError):
        if optional: return None
        raise ValueError('官方數字格式不符')


def normalized(row):
    if not isinstance(row, dict): raise ValueError('官方列格式不符')
    result = {}
    for key, value in row.items():
        clean = key.strip()
        if clean in result: raise ValueError('正規化欄名衝突')
        result[clean] = value
    return result


def base(symbol, key, dt, unit, values, period=None, published=None):
    if not re.fullmatch(r'[A-Za-z0-9]{4,12}', str(symbol)): raise ValueError('官方代號格式不符')
    return dict(symbol=str(symbol), key=key, data_date=dt, period=period,
                published_at=published, unit=unit, values=values)


def parse_source(source, payload, requested_date=None):
    if source not in SOURCES: raise ValueError('未知官方來源')
    result = []
    if source in ('institution', 'margin'):
        if not isinstance(payload, dict) or str(payload.get('stat')).lower() != 'ok':
            raise ValueError('官方報表未成功')
        dt = official_date(payload.get('date'))
        if requested_date != dt: raise ValueError('官方回傳日期不符')
        if source == 'institution':
            if payload.get('fields') != T86_FIELDS: raise ValueError('法人欄位結構改變')
            if '單位：股' not in str(payload.get('hints', '')): raise ValueError('法人股數單位未確認')
            table = payload
        else:
            tables = [t for t in payload.get('tables', []) if t.get('fields') == MARGIN_FIELDS]
            if len(tables) != 1: raise ValueError('信用交易欄位結構改變')
            table = tables[0]
            expected = [('股票', 2), ('融資', 6), ('融券', 6), ('', 1), ('', 1)]
            if [(g.get('title'), g.get('span')) for g in table.get('groups', [])] != expected:
                raise ValueError('信用交易群組結構改變')
        for row in table.get('data', []):
            if len(row) != len(table['fields']): raise ValueError('官方欄數不符')
            if source == 'institution':
                nums = {T86_FIELDS[i]: numeric(row[i]) for i in range(2, 19)}
                values = dict(foreign_net=nums[T86_FIELDS[4]], foreign_dealer_net=nums[T86_FIELDS[7]],
                    trust_net=nums[T86_FIELDS[10]], dealer_net=nums[T86_FIELDS[11]],
                    total_net=nums[T86_FIELDS[18]], official_fields=nums)
                unit = 'shares'
            else:
                nums = [numeric(x) for x in row[2:15]]
                values = dict(financing_previous=nums[3], financing_current=nums[4],
                    financing_redemption=nums[2], financing_limit=nums[5],
                    short_previous=nums[9], short_current=nums[10], short_redemption=nums[8],
                    short_limit=nums[11], offset=nums[12], note=str(row[15]).strip(),
                    note_applies='next_business_day', official_columns=nums)
                unit = 'trading_unit'
            result.append(base(row[0], dt, dt, unit, values))
    else:
        if not isinstance(payload, list) or not payload: raise ValueError('官方清單為空或格式不符')
        for raw in payload:
            row = normalized(raw)
            if source == 'revenue':
                period_raw = str(row['資料年月'])
                if not re.fullmatch(r'\d{5,6}', period_raw): raise ValueError('營收資料期不符')
                year = int(period_raw[:-2]) + (1911 if len(period_raw) == 5 else 0)
                period = date(year, int(period_raw[-2:]), 1).strftime('%Y-%m')
                yoy = numeric(row.get('營業收入-去年同月增減(%)'), True)
                if numeric(row.get('營業收入-去年當月營收'), True) in (None, 0): yoy = None
                values = dict(mom_pct=numeric(row.get('營業收入-上月比較增減(%)'), True),
                    yoy_pct=yoy, raw_amount=row.get('營業收入-當月營收'),
                    remark=str(row.get('備註', '')), export_date=official_date(row['出表日期']))
                result.append(base(row['公司代號'], period, period+'-01', 'amount_unverified', values, period))
            elif source == 'announcement':
                dt = official_date(row['發言日期'])
                published = None
                try:
                    clock = str(row['發言時間']).strip().zfill(6)
                    if not re.fullmatch(r'\d{6}', clock): raise ValueError('無效公告時刻')
                    published = datetime.fromisoformat(dt).replace(hour=int(clock[:2]),
                        minute=int(clock[2:4]), second=int(clock[4:]), tzinfo=TAIPEI).isoformat()
                except (ValueError, KeyError): pass
                values = dict(headline=str(row['主旨']), clause=str(row.get('符合條款', '')),
                    description=str(row.get('說明', '')), fact_date=official_date(row['事實發生日']),
                    time_status='verified' if published else 'unverified')
                # Separate multiple same-day announcements, while content corrections share event identity.
                key = dt+'|'+str(row.get('發言時間', ''))+'|'+values['headline']
                result.append(base(row['公司代號'], key, dt, 'text', values, published=published))
            else:
                dt = official_date(row['Date'])
                values = dict(type=str(row.get('Exdividend', '')), cash_dividend=numeric(row.get('CashDividend'), True))
                result.append(base(row['Code'], dt, dt, 'official_dividend', values))
    identities = [(r['symbol'], r['key']) for r in result]
    if len(identities) != len(set(identities)): raise ValueError('官方資料鍵重複')
    if not result: raise ValueError('官方資料沒有有效列')
    return result
