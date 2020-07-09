from decimal import Decimal
import os
import pytest

from queue import Queue
import pandas as pd

from savoia.portfolio.portfolio import Portfolio
from savoia.datafeed.ticker import Ticker
from savoia.config.dir_config import OUTPUT_RESULTS_DIR
from savoia.event.event import Event, SignalEvent, OrderEvent, FillEvent, \
    TickEvent
from savoia.types.types import Pair


# ================================================================
# update_position_price()
# ================================================================
@pytest.fixture(scope='function')
def TickerMock() -> Ticker:
    _pairs = ["GBPUSD", "USDJPY"]
    _prices = {
        "GBPUSD": {"bid": Decimal("1.2541"), "ask": Decimal("1.2543")},
        "USDJPY": {"bid": Decimal("107.25"), "ask": Decimal("107.80")},
    }
    tm = Ticker(_pairs)
    # Create decimalaised prices for trade pair
    for pair, price in _prices.items():
        _bid, _ask = price['bid'], price['ask']
        tm.prices[pair]["bid"] = _bid
        tm.prices[pair]["ask"] = _ask
        # Create decimalised prices for inverted pair
        inv_pair, inv_bid, inv_ask = tm.invert_prices(pair, _bid, _ask)
        tm.prices[inv_pair]["bid"] = inv_bid
        tm.prices[inv_pair]["ask"] = inv_ask
    return tm


@pytest.fixture(scope='function')
def port(TickerMock: Ticker) -> Portfolio:
    ticker = TickerMock
    events: 'Queue[Event]' = Queue()
    home_currency = "JPY"
    pairs = ['GBPUSD', 'USDJPY']
    equity = Decimal("1234567")
    port = Portfolio(ticker, events, home_currency, pairs, equity)
    return port


def test_init_(port: Portfolio, TickerMock: Ticker) -> None:
    assert port.ticker is TickerMock
    assert isinstance(port.events_queue, Queue)
    assert port.home_currency == 'JPY'
    assert port.equity == Decimal('1234567')
    assert port.balance == Decimal('1234567')
    assert port.upl == Decimal('0')
    assert port.pairs == ['GBPUSD', 'USDJPY']
    assert port.isBacktest
    assert len(port.positions) == 2


def test_create_equity_file(port: Portfolio) -> None:
    out_file = port._create_equity_file()
    filepath = os.path.join(OUTPUT_RESULTS_DIR, "backtest.csv")
    assert out_file.name == str(filepath)
    assert os.path.isfile(filepath)

    out_file.close()
    with open(filepath, "r") as f:
        assert f.read() == "Timestamp,Balance,GBPUSD,USDJPY\n"


@pytest.mark.parametrize("pair, order_type, units, time, price, ref", [
    ("GBPUSD", "limit", "3000", "2020-07-08 12:00:00", '1.234', '11111'),
    ("USDJPY", "market", "-0.9", "2020-07-09 03:03:50", None, '11111'),
])
def test_execute_signal(pair: str, order_type: str, units: str, time: str,
        price: str, port: Portfolio, ref: str) -> None:
    _price = None if price is None else Decimal(price)
    port.execute_signal(SignalEvent(ref, pair, order_type, Decimal(units),
        pd.Timestamp(time), _price))
    _order: OrderEvent = port.events_queue.get()
    
    assert _order.instrument == pair
    assert _order.units == Decimal(units)
    assert _order.order_type == order_type
    assert _order.time == pd.Timestamp(time)
    assert _order.price == _price


@pytest.mark.parametrize("pair, order_type, units, time, quote, ref", [
    ("GBPUSD", "market", "3000", "2020-07-08 12:00:00", "ask", "11111"),
    ("USDJPY", "market", "-0.9", "2020-07-09 03:03:50", "bid", "22222"),
])
def test_execute_signal_lackofticker(port: Portfolio,
                                    pair: str,
                                    order_type: str,
                                    units: str,
                                    time: str,
                                    quote: str, ref: str) -> None:
    from testfixtures import LogCapture

    tmp = port.ticker.prices[pair][quote]
    port.ticker.prices[pair][quote] = None
    print(port.ticker.prices[pair])
    with LogCapture() as log:
        port.execute_signal(event=SignalEvent(ref, pair, order_type,
            Decimal(units), pd.Timestamp(time)))
        log.check(
            ('savoia.portfolio.portfolio', 'INFO', "Unable to execute order " +
             'as price data was insufficient.')
        )
    port.ticker.prices[pair][quote] = tmp


# ================================================================
# execute_fill()
# ================================================================
@pytest.fixture(scope='function')
def port1(TickerMock1: Ticker) -> Portfolio:
    ticker = TickerMock1
    events: 'Queue[Event]' = Queue()
    home_currency = "JPY"
    pairs = ['GBPUSD', 'USDJPY']
    equity = Decimal("100000")
    port1 = Portfolio(ticker, events, home_currency, pairs, equity)
    return port1


@pytest.fixture(scope='function')
def TickerMock1() -> Ticker:
    _pairs = ["GBPUSD", "EURUSD", "USDJPY"]
    _prices = {
        "GBPUSD": {"bid": Decimal("1.30328"), "ask": Decimal("1.50349")},
        "USDJPY": {"bid": Decimal("105.774"), "ask": Decimal("110.863")},
    }
    tm = Ticker(_pairs)
    # Create decimalaised prices for trade pair
    for pair, price in _prices.items():
        _bid, _ask = price['bid'], price['ask']
        tm.prices[pair]["bid"] = _bid
        tm.prices[pair]["ask"] = _ask
        # Create decimalised prices for inverted pair
        inv_pair, inv_bid, inv_ask = tm.invert_prices(pair, _bid, _ask)
        tm.prices[inv_pair]["bid"] = inv_bid
        tm.prices[inv_pair]["ask"] = inv_ask
    return tm


# pair, home_currency, exec_price, units, exit_price, exit_units,
# equity, exp_balance, exp_upl, exp_equity
data5 = [
    ('GBPUSD', 'JPY', '1.40349', '-1400', '1.3', '1800',
     '10000', '25325.1717640', '138.77548800', '25463.9472520'),
    ('USDJPY', 'JPY', '106.074', '4.8', '108', '-8.3',
    '100', '109.244800', '-10.02050 ', '99.22430')
]


@pytest.mark.parametrize('pair, home_currency, exec_price, units,' +
                    'exit_price, exit_units,' +
                    'equity, exp_balance, exp_upl, exp_equity', data5)
def test_execute_fill_exit_entry(
        pair: Pair, home_currency: str, exec_price: str, units: str,
        exit_price: str, exit_units: str,
        equity: str, exp_balance: str, exp_upl: str, exp_equity: str,
        TickerMock1: Ticker) -> None:
    port = Portfolio(TickerMock1, Queue(), home_currency, ['GBPUSD', 'USDJPY'],
        Decimal(equity), True)
    port.execute_fill(FillEvent('ref123', pair, Decimal(units),
        Decimal(exec_price), 'filled', pd.Timestamp('2020-07-08 21:56:00')))
    port.execute_fill(FillEvent('ref123', pair, Decimal(exit_units),
        Decimal(exit_price), 'filled', pd.Timestamp('2020-07-08 21:56:00')))
    
    assert port.balance == Decimal(exp_balance)
    assert port.upl == Decimal(exp_upl)
    assert port.equity == Decimal(exp_equity)


# ================================================================
# update_portfolio()
# ================================================================
@pytest.fixture(scope='function')
def TickerMock2() -> Ticker:
    _pairs = ["GBPUSD", "EURUSD", "USDJPY"]
    _prices = {
        "GBPUSD": {"bid": Decimal("1.2541"), "ask": Decimal("1.2543")},
        "USDJPY": {"bid": Decimal("107.25"), "ask": Decimal("107.80")},
    }
    tm = Ticker(_pairs)
    # Create decimalaised prices for trade pair
    for pair, price in _prices.items():
        _bid, _ask = price['bid'], price['ask']
        tm.prices[pair]["bid"] = _bid
        tm.prices[pair]["ask"] = _ask
        # Create decimalised prices for inverted pair
        inv_pair, inv_bid, inv_ask = tm.invert_prices(pair, _bid, _ask)
        tm.prices[inv_pair]["bid"] = inv_bid
        tm.prices[inv_pair]["ask"] = inv_ask
    return tm


data6 = [
    ('JPY', 'GBPUSD', '1.60328', '1200', '100000',
        '100000', '-44408.106', '55591.894'),
    ('JPY', 'GBPUSD', '1.40349', '-200', '5000',
        '5000', '3229.6455', '8229.6455'),
    ('JPY', 'USDJPY', '91.7740', '0.80', '15',
        '15', '12.3808', '27.3808'),
    ('JPY', 'USDJPY', '113.063', '-0.5', '4',
        '4', '2.6315', '6.6315')
]


@pytest.mark.parametrize('home_currency, pair, exec_price, units, equity,' +
                         'exp_balance, exp_upl, exp_equity', data6)
def test_update_portfolio(home_currency: str, pair: Pair, exec_price: str,
        units: str, equity: str, exp_balance: str, exp_upl: str,
        exp_equity: str, TickerMock1: Ticker, TickerMock2: Ticker) -> None:
    port = Portfolio(TickerMock1, Queue(), home_currency,
        ["GBPUSD", "EURUSD", "USDJPY"], Decimal(equity), True)
    port.execute_fill(FillEvent('ref123', pair, Decimal(units),
        Decimal(exec_price), 'filled', pd.Timestamp('2020-07-08 21:56:00')))
    
    for _pair in ['USDJPY', 'GBPUSD']:
        bid = TickerMock2.prices[_pair]['bid']
        ask = TickerMock2.prices[_pair]['ask']

        TickerMock1.prices[_pair]["bid"] = bid
        TickerMock1.prices[_pair]["ask"] = ask

        # Create decimalised prices for inverted pair
        inv_pair, inv_bid, inv_ask = TickerMock2.invert_prices(_pair, bid, ask)
        TickerMock1.prices[inv_pair]["bid"] = inv_bid
        TickerMock1.prices[inv_pair]["ask"] = inv_ask

    port.update_portfolio(TickEvent(pair, pd.Timestamp('2020-07-08 21:56:00'),
        Decimal('111'), Decimal('222')))
    
    assert port.balance == Decimal(exp_balance)
    assert port.upl == Decimal(exp_upl)
    assert port.equity == Decimal(exp_equity)
