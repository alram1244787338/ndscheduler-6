/**
 * Base table view that encapsulates shared DataTable lifecycle logic.
 *
 * Provides:
 *  - Collection event wiring (sync → render, request → loading, error → alert)
 *  - DataTable initialization with overridable options
 *  - Clear-table + spinner on request start
 *  - Error alert + spinner stop on request failure
 *  - Row-building render loop with an afterRender() hook for subclasses
 *  - Safe DOM event binding helper (off-then-on) to avoid duplicate handlers
 *
 * Subclasses override:
 *  - tableId          : DOM id of the <table> element
 *  - spinnerId        : DOM id of the spinner container
 *  - dataTableOptions : options hash passed to $.dataTable()
 *  - buildRows()      : returns an array of row arrays for DataTable
 *  - afterRender()    : optional hook called after data is added to the table
 *  - refreshCollection(): called to (re-)fetch data from the server
 *
 * @refactor extracted from jobs/table-view, executions/table-view, logs/table-view
 */

require.config({
  paths: {
    'jquery': 'vendor/jquery',
    'underscore': 'vendor/underscore',
    'backbone': 'vendor/backbone',
    'bootstrap': 'vendor/bootstrap',
    'datatables': 'vendor/jquery.dataTables',
    'utils': 'utils'
  },

  shim: {
    'bootstrap': {
      deps: ['jquery']
    },
    'backbone': {
      deps: ['underscore', 'jquery'],
      exports: 'Backbone'
    },
    'datatables': {
      deps: ['jquery'],
      exports: '$.fn.dataTable'
    }
  }
});

define(['utils',
        'backbone',
        'bootstrap',
        'datatables'], function(utils) {
  'use strict';

  return Backbone.View.extend({

    /** DOM id of the <table> element — must be set by subclass. */
    tableId: null,

    /** DOM id of the spinner container — must be set by subclass. */
    spinnerId: null,

    /**
     * DataTable initialization options.
     * Subclasses can override to customise sorting, column defs, etc.
     * @return {object} options hash for $.dataTable()
     */
    dataTableOptions: function() {
      return {};
    },

    /**
     * Build the array of row data to feed into DataTable.
     * Must be implemented by subclasses.
     *
     * @return {Array} array of row arrays
     */
    buildRows: function() {
      return [];
    },

    /**
     * Optional hook called after render completes (data added, spinner stopped).
     * Subclasses can override to attach extra behaviour (sub-views, tooltips, etc).
     */
    afterRender: function() {},

    /**
     * Trigger a fresh data fetch on the collection.
     * Subclasses should override if the collection has a named fetch method.
     */
    refreshCollection: function() {
      // no-op by default; subclasses wire this up
    },

    // ------------------------------------------------------------------
    // Lifecycle
    // ------------------------------------------------------------------

    initialize: function() {
      this._bindCollectionEvents();
      this._initDataTable();
      this._bindDOMEvents();
    },

    /**
     * Wire up collection listeners.  Using listenTo ensures automatic
     * cleanup when the view is removed.
     */
    _bindCollectionEvents: function() {
      this.listenTo(this.collection, 'sync', this.render);
      this.listenTo(this.collection, 'request', this.requestRender);
      this.listenTo(this.collection, 'error', this.requestError);
    },

    /**
     * Initialise the DataTable widget.
     */
    _initDataTable: function() {
      var opts = _.result(this, 'dataTableOptions') || {};
      this.table = $('#' + this.tableId).dataTable(opts);
    },

    /**
     * Hook for subclasses to bind extra DOM events.
     * Called during initialize after collection listeners and DataTable setup.
     * Use safeBind() inside to prevent duplicate handlers.
     */
    _bindDOMEvents: function() {
      // no-op — subclasses override
    },

    // ------------------------------------------------------------------
    // Safe event binding helper
    // ------------------------------------------------------------------

    /**
     * Bind a DOM event handler safely — calls .off() first to remove
     * any previously attached handler for the same event, then .on().
     *
     * This prevents duplicate bindings when a view is re-initialised
     * (e.g. after a tab switch or hot-reload).
     *
     * @param {string|jQuery} selector  jQuery selector or element
     * @param {string}        event     event name (e.g. 'click')
     * @param {function}      handler   callback (will be bound to `this`)
     */
    safeBind: function(selector, event, handler) {
      var $el = (selector instanceof $) ? selector : $(selector);
      $el.off(event).on(event, _.bind(handler, this));
    },

    // ------------------------------------------------------------------
    // Collection event handlers
    // ------------------------------------------------------------------

    /**
     * Called when a network request starts — clear the table and show spinner.
     */
    requestRender: function() {
      this.table.fnClearTable();
      this.spinner = utils.startSpinner(this.spinnerId);
    },

    /**
     * Called when a network request fails — stop spinner and show error.
     *
     * @param {object} model
     * @param {object} response
     * @param {object} options
     */
    requestError: function(model, response, options) {
      if (this.spinner) {
        this.spinner.stop();
      }
      utils.alertError('Request failed: ' + response.responseText);
    },

    /**
     * Called when collection sync completes — build rows, populate table,
     * stop spinner, then call afterRender() hook.
     */
    render: function() {
      var data = this.buildRows();

      if (data.length) {
        this.table.fnClearTable();
        this.table.fnAddData(data);
      }

      // Stop the spinner
      if (this.spinner) {
        this.spinner.stop();
      }

      this.afterRender();
    }
  });
});
